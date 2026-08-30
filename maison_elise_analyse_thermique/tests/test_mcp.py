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
            "thermal_facts": {"facts": [{"id": "deterministic", "label": "Fait", "value": 1}]},
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


class RecordingPublisher:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def publish(self, result: dict) -> dict:
        self.calls.append(result)
        return {"enabled": True, "status": "sent", "service": "notify.test"}


class NeverLoadSource:
    def load(self, start: datetime, end: datetime):
        raise AssertionError("invalid periods must fail before reading the data source")


def _test_mcp_app(service, now_provider=None, notification_publisher=None) -> tuple[FastAPI, object]:
    mcp_server = build_mcp_server(
        service,
        timezone="Europe/Paris",
        now_provider=now_provider,
        notification_publisher=notification_publisher,
    )
    test_app = FastAPI()
    test_app.mount("/", mcp_server.streamable_http_app())
    return test_app, mcp_server


@asynccontextmanager
async def _session_for(service, now_provider=None, notification_publisher=None):
    test_app, mcp_server = _test_mcp_app(
        service,
        now_provider=now_provider,
        notification_publisher=notification_publisher,
    )
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


def test_list_tools_exposes_ergonomic_analysis_contract() -> None:
    async def scenario() -> None:
        async with _session_for(RecordingService()) as session:
            await session.initialize()
            tools = await session.list_tools()
            assert len(tools.tools) == 1
            tool = tools.tools[0]
            assert tool.name == "AnalyseThermique"
            assert set(tool.inputSchema["properties"]) == {
                "mode",
                "start",
                "end",
                "compare",
                "day",
                "start_time",
                "end_time",
            }
            assert set(tool.inputSchema["required"]) == {"mode"}
            assert tool.inputSchema["properties"]["mode"]["enum"] == [
                "current_h2",
                "relative_day",
                "explicit",
                "last_result",
            ]
            assert "Analyse heure" in tool.description
            assert "mode=current_h2" in tool.description
            assert "mode=relative_day" in tool.description
            assert "donne-moi le détail" in tool.description
            assert "mode=last_result" in tool.description
            assert "constat, analyse prudente" in tool.description
            assert "0 %=fermé, 100 %=ouvert" in tool.description
            assert "ne jamais parler de demain" in tool.description

    asyncio.run(scenario())


def test_call_tool_returns_core_json_plus_interaction_contract() -> None:
    async def scenario() -> None:
        service = RecordingService()
        async with _session_for(service) as session:
            await session.initialize()
            result = await session.call_tool(
                "AnalyseThermique",
                {
                    "mode": "explicit",
                    "start": "2026-08-29T00:00:00+02:00",
                    "end": "2026-08-30T00:00:00+02:00",
                },
            )

        assert result.isError is False
        assert result.structuredContent is not None
        structured = result.structuredContent
        assert structured["period"] == {
            "start": "2026-08-29T00:00:00+02:00",
            "end": "2026-08-30T00:00:00+02:00",
        }
        assert structured["analysis"] == {"marker": "deterministic"}
        assert structured["interaction_contract"]["voice_short_response"]["order"] == [
            "constat",
            "analyse",
            "preconisation",
            "a_venir",
        ]
        assert structured["interaction_contract"]["shutter_position_semantics"]["100"] == "fully_open"
        assert structured["automatic_notification"]["status"] == "disabled"
        assert json.loads(result.content[0].text) == structured
        assert len(service.calls) == 1

    asyncio.run(scenario())


def test_call_tool_forwards_optional_comparison() -> None:
    async def scenario() -> None:
        service = RecordingService()
        async with _session_for(service) as session:
            await session.initialize()
            result = await session.call_tool(
                "AnalyseThermique",
                {
                    "mode": "explicit",
                    "start": "2026-08-29T00:00:00+02:00",
                    "end": "2026-08-30T00:00:00+02:00",
                    "compare": "previous_day",
                },
            )

        assert result.isError is False
        assert result.structuredContent["comparison"]["mode"] == "previous_day"
        assert service.calls[0][2] == "previous_day"

    asyncio.run(scenario())


def test_current_h2_uses_app_clock_and_ignores_llm_dates_and_compare() -> None:
    async def scenario() -> None:
        clear_diagnostics()
        service = RecordingService()
        fixed_now = datetime.fromisoformat("2026-08-30T18:30:00+02:00")
        async with _session_for(service, now_provider=lambda: fixed_now) as session:
            await session.initialize()
            result = await session.call_tool(
                "AnalyseThermique",
                {
                    "mode": "current_h2",
                    "start": "2023-10-16T14:00:00+02:00",
                    "end": "2023-10-16T15:00:00+02:00",
                    "compare": "previous_day",
                },
            )

        assert result.isError is False
        assert len(service.calls) == 1
        start, end, compare = service.calls[0]
        assert start == datetime.fromisoformat("2026-08-30T16:30:00+02:00")
        assert end == fixed_now
        assert compare is None
        assert result.structuredContent["interaction_context"]["voice_request_alias"] == "Analyse heure"
        text = diagnostics_text()
        assert 'MCP_DIAG resolution' in text
        assert '"mode":"current_h2"' in text
        assert '"received_start":"2023-10-16T14:00:00+02:00"' in text
        assert '"resolved_start":"2026-08-30T16:30:00+02:00"' in text
        assert '"resolved_end":"2026-08-30T18:30:00+02:00"' in text
        assert '"resolved_compare":null' in text

    asyncio.run(scenario())


def test_relative_day_resolves_today_and_yesterday_with_app_clock() -> None:
    async def scenario() -> None:
        service = RecordingService()
        fixed_now = datetime.fromisoformat("2026-08-30T19:00:00+02:00")
        async with _session_for(service, now_provider=lambda: fixed_now) as session:
            await session.initialize()
            today = await session.call_tool(
                "AnalyseThermique",
                {
                    "mode": "relative_day",
                    "day": "today",
                    "start_time": "13",
                    "end_time": "17:00",
                },
            )
            yesterday = await session.call_tool(
                "AnalyseThermique",
                {
                    "mode": "relative_day",
                    "day": "yesterday",
                    "start_time": "08:00",
                    "end_time": "15:00",
                },
            )

        assert today.isError is False
        assert yesterday.isError is False
        assert service.calls[0][0] == datetime.fromisoformat("2026-08-30T13:00:00+02:00")
        assert service.calls[0][1] == datetime.fromisoformat("2026-08-30T17:00:00+02:00")
        assert service.calls[1][0] == datetime.fromisoformat("2026-08-29T08:00:00+02:00")
        assert service.calls[1][1] == datetime.fromisoformat("2026-08-29T15:00:00+02:00")

    asyncio.run(scenario())


def test_last_result_reuses_same_analysis_without_recalculation_or_notification() -> None:
    async def scenario() -> None:
        service = RecordingService()
        publisher = RecordingPublisher()
        async with _session_for(service, notification_publisher=publisher) as session:
            await session.initialize()
            first = await session.call_tool(
                "AnalyseThermique",
                {
                    "mode": "explicit",
                    "start": "2026-08-29T13:00:00+02:00",
                    "end": "2026-08-29T17:00:00+02:00",
                },
            )
            detail = await session.call_tool("AnalyseThermique", {"mode": "last_result"})

        assert first.isError is False
        assert detail.isError is False
        assert len(service.calls) == 1
        assert len(publisher.calls) == 1
        assert detail.structuredContent["period"] == first.structuredContent["period"]
        assert detail.structuredContent["interaction_context"] == {
            "reused_previous_analysis": True,
            "fresh_analysis": False,
            "automatic_notification_repeated": False,
        }

    asyncio.run(scenario())


def test_explicit_mode_requires_start_and_end() -> None:
    async def scenario() -> None:
        async with _session_for(RecordingService()) as session:
            await session.initialize()
            result = await session.call_tool(
                "AnalyseThermique",
                {"mode": "explicit"},
            )
        assert result.isError is True
        assert "start and end are required when mode=explicit" in result.content[0].text

    asyncio.run(scenario())


def test_relative_day_rejects_invalid_local_window() -> None:
    async def scenario() -> None:
        fixed_now = datetime.fromisoformat("2026-08-30T19:00:00+02:00")
        async with _session_for(RecordingService(), now_provider=lambda: fixed_now) as session:
            await session.initialize()
            result = await session.call_tool(
                "AnalyseThermique",
                {
                    "mode": "relative_day",
                    "day": "today",
                    "start_time": "17:00",
                    "end_time": "13:00",
                },
            )
        assert result.isError is True
        assert "end_time must be after start_time" in result.content[0].text

    asyncio.run(scenario())


def test_mcp_diagnostic_records_request_result_and_copy_page() -> None:
    async def scenario() -> None:
        clear_diagnostics()
        async with _session_for(RecordingService()) as session:
            await session.initialize()
            result = await session.call_tool(
                "AnalyseThermique",
                {
                    "mode": "explicit",
                    "start": "2026-08-29T00:00:00+02:00",
                    "end": "2026-08-30T00:00:00+02:00",
                    "compare": "previous_day",
                },
            )
        assert result.isError is False

    asyncio.run(scenario())

    text = diagnostics_text()
    assert 'MCP_DIAG resolution' in text
    assert '"mode":"explicit"' in text
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
    assert "MCP_DIAG resolution" in page_text
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
                {"mode": "explicit", "start": start, "end": end},
            )

        assert result.isError is True
        assert result.structuredContent is None
        assert message in result.content[0].text

    asyncio.run(scenario())
