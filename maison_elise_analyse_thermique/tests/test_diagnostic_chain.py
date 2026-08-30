from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI
import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from app.diagnostics import clear_diagnostics, diagnostics_text
from app.mcp_server import build_mcp_server


class CalculationChainService:
    def analyse(self, start: datetime, end: datetime, compare: str | None = None) -> dict:
        return {
            "period": {"start": start.isoformat(), "end": end.isoformat()},
            "analysis": {
                "raw_samples": 290,
                "samples": 289,
                "input_quality": {"near_duplicate_dropped_count": 1},
                "temperature_indoor": {"mean": 20.87, "coverage": 1.0},
                "temperature_outdoor_reference": {"mean": 18.49, "coverage": 1.0},
                "quality": {
                    "outdoor_temperature_suspect_count": 0,
                    "outdoor_temperature_rejected_count": 0,
                },
                "period_coverage": {"coverage": 0.997},
            },
            "thermal_facts": {"facts": []},
            "comparison": {
                "mode": compare,
                "period": {
                    "start": "2026-08-28T00:00:00+02:00",
                    "end": "2026-08-28T23:59:59+02:00",
                },
                "analysis": {
                    "raw_samples": 288,
                    "samples": 288,
                    "input_quality": {"near_duplicate_dropped_count": 0},
                    "temperature_indoor": {"mean": 20.59, "coverage": 1.0},
                    "temperature_outdoor_reference": {"mean": 18.49, "coverage": 1.0},
                    "quality": {
                        "outdoor_temperature_suspect_count": 0,
                        "outdoor_temperature_rejected_count": 0,
                    },
                    "period_coverage": {"coverage": 0.997},
                },
                "delta": {
                    "temperature_indoor_mean_delta_c": 0.28,
                    "temperature_outdoor_mean_delta_c": 0.0,
                    "cooling_while_any_opening_minutes_delta": -35.0,
                },
            },
        }


@asynccontextmanager
async def _session_for(service):
    mcp_server = build_mcp_server(service)
    app = FastAPI()
    app.mount("/", mcp_server.streamable_http_app())
    transport = httpx.ASGITransport(app=app)
    async with mcp_server.session_manager.run():
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            async with streamable_http_client(
                "http://testserver/mcp",
                http_client=client,
                terminate_on_close=False,
            ) as (read_stream, write_stream, _):
                async with ClientSession(read_stream, write_stream) as session:
                    yield session


def test_mcp_diagnostic_traces_loaded_deduplicated_means_and_deltas() -> None:
    async def scenario() -> None:
        clear_diagnostics()
        async with _session_for(CalculationChainService()) as session:
            await session.initialize()
            result = await session.call_tool(
                "AnalyseThermique",
                {
                    "start": "2026-08-29T00:00:00+02:00",
                    "end": "2026-08-29T23:59:59+02:00",
                    "compare": "previous_day",
                },
            )
            assert result.isError is False

    asyncio.run(scenario())

    text = diagnostics_text()
    assert "MCP_DIAG current_analysis" in text
    assert '"raw_samples":290' in text
    assert '"samples_after_dedup":289' in text
    assert '"near_duplicate_dropped_count":1' in text
    assert '"temperature_indoor_mean_c":20.87' in text
    assert '"temperature_outdoor_mean_c":18.49' in text

    assert "MCP_DIAG reference_analysis" in text
    assert '"raw_samples":288' in text
    assert '"samples_after_dedup":288' in text
    assert '"temperature_indoor_mean_c":20.59' in text

    assert "MCP_DIAG result" in text
    assert '"temperature_indoor_mean_delta_c":0.28' in text
    assert '"temperature_outdoor_mean_delta_c":0.0' in text
    assert '"cooling_while_any_opening_minutes_delta":-35.0' in text
