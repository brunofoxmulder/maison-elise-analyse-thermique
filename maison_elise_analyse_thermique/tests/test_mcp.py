from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime
import json

from fastapi import FastAPI
from fastapi.testclient import TestClient
import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
import pytest

from app.api import APP_VERSION, app, diagnostic as diagnostic_page
from app.diagnostics import clear_diagnostics, diagnostics_text
from app.mcp_server import build_mcp_server
from app.service import ThermalAnalysisService


class RecordingService:
    """Small spy used to verify the MCP facade without exercising the engine."""

    def __init__(self) -> None:
        self.calls: list[tuple[datetime, datetime, str | None]] = []

    def analyse(
        self,
        start: datetime,
        end: datetime,
        compare: str | None = None,
    ) -> dict:
        self.calls.append((start, end, compare))
        result = {
            "period": {"start": start.isoformat(), "end": end.isoformat()},
            "analysis": {"marker": "deterministic"},
            "thermal_facts": [{"fact": "deterministic"}],
        }
        if compare is not None:
            result["comparison"] = {
                "mode": compare,
                "period": {
                    "start": "2026-08-28T00:00:00+02:00",
                    "end": "2026-08-29T00:00:00+02:00",
                },
                "delta": {
                    "temperature_indoor_mean_delta_c": 0.28,
                    "temperature_outdoor_mean_delta_c": 0.0,
                    "cooling_while_any_opening_minutes_delta": -35.0,
                },
            }
        return result


class NeverLoadSource:
    def load(self, start: datetime, end: datetime):
        raise AssertionError("invalid periods must fail before reading the data source")


def _test_mcp_app(service) -> tuple[FastAPI, object]:
    mcp_server = build_mcp_server(service)
    test_app = FastAPI()
    test_app.mount("/", mcp_server.streamable_http_app())
    return test_app, mcp_server


@asynccontextmanager
async def _session_for(service):
    test_app, mcp_server = _test_mcp_app(service)
    transport = httpx.ASGITransport(app=test_app)
    async with mcp_server.session_manager.run():
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as http_client:
            async with streamable_http_client(
                "http://testserver/mcp",
                http_client=http_client,
                terminate_on_close=False,
            ) as (read_stream, write_stream, _):
                async with ClientSession(read_stream, write_stream) as session:
                    yield session


def test_legacy_http_contract_is_preserved() -> None:
    with TestClient(app) as client:
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {
            "status": "ok",
            "version": APP_VERSION,
            "read_only": True,
            "data_source": "InMemoryDataSource",
        }

        diagnostic = client.get("/diagnostic")
        assert diagnostic.status_code == 200
        assert "Copier le diagnostic" in diagnostic.text
        assert 'id="diag"' in diagnostic.text
        assert APP_VERSION in diagnostic.text

    route_paths = {getattr(route, "path", None) for route in app.routes}
    assert "/health" in route_paths
    assert "/diagnostic" in route_paths
    assert "/analyse" in route_paths
    assert "/analyse/natural" in route_paths


def test_initialize_twice_like_home_assistant_config_flow() -> None:
    async def scenario() -> None:
        async with _session_for(RecordingService()) as session:
            first = await session.initialize()
            second = await session.initialize()
            assert first.capabilities.tools is not None
            assert second.capabilities.tools is not None

    asyncio.run(scenario())


def test_list_tools_exposes_only_analyse_thermique() -> None:
    async def scenario() -> None:
        async with _session_for(RecordingService()) as session:
            await session.initialize()
            tools = await session.list_tools()
            assert len(tools.tools) == 1
            tool = tools.tools[0]
            assert tool.name == "AnalyseThermique"
            assert set(tool.inputSchema["properties"]) == {"start", "end", "compare"}
            assert set(tool.inputSchema["required"]) == {"start", "end"}
            assert "last_hour est le sujet principal" in tool.description
            assert "analysis_contract" in tool.description
            assert "Fait / Observation / Hypothèse / Incertitude" in tool.description
            assert "température Daikin terrasse" in tool.description
            assert "plus frais" in tool.description
            assert "forecast_h4" in tool.description
            assert "NORMAL / VIGILANCE / ALERTE" in tool.description

    asyncio.run(scenario())


def test_call_tool_returns_json_as_structured_content() -> None:
    async def scenario() -> None:
        service = RecordingService()
        async with _session_for(service) as session:
            await session.initialize()
            result = await session.call_tool(
                "AnalyseThermique",
                {
                    "start": "2026-08-29T00:00:00+02:00",
                    "end": "2026-08-30T00:00:00+02:00",
                },
            )

        assert result.isError is False
        assert result.structuredContent is not None
        assert result.structuredContent == {
            "period": {
                "start": "2026-08-29T00:00:00+02:00",
                "end": "2026-08-30T00:00:00+02:00",
            },
            "analysis": {"marker": "deterministic"},
            "thermal_facts": [{"fact": "deterministic"}],
        }
        assert json.loads(result.content[0].text) == result.structuredContent
        assert len(service.calls) == 1
        start, end, compare = service.calls[0]
        assert start == datetime.fromisoformat("2026-08-29T00:00:00+02:00")
        assert end == datetime.fromisoformat("2026-08-30T00:00:00+02:00")
        assert compare is None

    asyncio.run(scenario())


def test_call_tool_forwards_optional_comparison() -> None:
    async def scenario() -> None:
        service = RecordingService()
        async with _session_for(service) as session:
            await session.initialize()
            result = await session.call_tool(
                "AnalyseThermique",
                {
                    "start": "2026-08-29T00:00:00+02:00",
                    "end": "2026-08-30T00:00:00+02:00",
                    "compare": "previous_day",
                },
            )

        assert result.isError is False
        assert result.structuredContent["comparison"]["mode"] == "previous_day"
        assert service.calls[0][2] == "previous_day"

    asyncio.run(scenario())


def test_mcp_diagnostic_records_request_result_and_copy_page() -> None:
    async def scenario() -> None:
        clear_diagnostics()
        async with _session_for(RecordingService()) as session:
            await session.initialize()
            result = await session.call_tool(
                "AnalyseThermique",
                {
                    "start": "2026-08-29T00:00:00+02:00",
                    "end": "2026-08-30T00:00:00+02:00",
                    "compare": "previous_day",
                },
            )
        assert result.isError is False

    asyncio.run(scenario())

    text = diagnostics_text()
    assert 'MCP_DIAG request' in text
    assert '"start":"2026-08-29T00:00:00+02:00"' in text
    assert '"end":"2026-08-30T00:00:00+02:00"' in text
    assert '"compare":"previous_day"' in text
    assert 'MCP_DIAG result' in text
    assert '"temperature_indoor_mean_delta_c":0.28' in text
    assert '"temperature_outdoor_mean_delta_c":0.0' in text
    assert '"cooling_while_any_opening_minutes_delta":-35.0' in text

    page = diagnostic_page()
    page_text = page.body.decode("utf-8")
    assert page.status_code == 200
    assert "Copier le diagnostic" in page_text
    assert "MCP_DIAG request" in page_text
    assert "MCP_DIAG result" in page_text


@pytest.mark.parametrize(
    ("start", "end", "message"),
    [
        (
            "2026-08-30T00:00:00+02:00",
            "2026-08-29T00:00:00+02:00",
            "end must be after start",
        ),
        (
            "2026-08-29T00:00:00",
            "2026-08-30T00:00:00",
            "start/end must be timezone-aware",
        ),
    ],
)
def test_period_errors_are_reported_by_the_existing_service(
    start: str,
    end: str,
    message: str,
) -> None:
    async def scenario() -> None:
        service = ThermalAnalysisService(NeverLoadSource())
        async with _session_for(service) as session:
            await session.initialize()
            result = await session.call_tool(
                "AnalyseThermique",
                {"start": start, "end": end},
            )

        assert result.isError is True
        assert result.structuredContent is None
        assert message in result.content[0].text

    asyncio.run(scenario())
