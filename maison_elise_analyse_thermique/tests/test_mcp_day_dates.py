from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI
import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from app.mcp_server import build_mcp_server


class RecordingService:
    def __init__(self) -> None:
        self.calls = []

    def analyse(self, start, end, compare=None):
        self.calls.append((start, end, compare))
        return {
            "period": {"start": start.isoformat(), "end": end.isoformat()},
            "analysis": {"marker": "day"},
            "thermal_facts": {"facts": []},
            "setpoint_profiles": {
                "dominant_active_hvac_mode": "cool",
                "modes": {
                    "cool": {
                        "total_minutes": 1200.0,
                        "distinct_requested_temperatures_c": [21.0, 23.0],
                        "dominant_two_requested_temperatures_c": [21.0, 23.0],
                        "regimes": [],
                    }
                },
                "setpoint_source_rule": "recorded_Consigne_is_truth_never_hardcode_requested_temperatures",
            },
        }


class RecordingPublisher:
    def __init__(self) -> None:
        self.calls = []

    def publish(self, report):
        self.calls.append(report)
        return {
            "enabled": True,
            "status": "sent",
            "service": "persistent_notification.create",
            "analysis_id": report["analysis_id"],
        }


@asynccontextmanager
async def _session_for(service, now_provider, publisher=None):
    mcp_server = build_mcp_server(
        service,
        timezone="Europe/Paris",
        now_provider=now_provider,
        notification_publisher=publisher,
    )
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


def _day_report_payload(analysis_id):
    return {
        "analysis_id": analysis_id,
        "profile": "day",
        "status": "NORMAL",
        "short_response": "La journée est stable et les deux consignes enregistrées ont été suivies correctement.",
        "situation": "Le salon est resté thermiquement stable sur la journée.",
        "setpoints": "Consigne 21 °C puis 23 °C, avec suivi analysé séparément pour chaque plage.",
        "evolution": "Aucune dérive durable n'est observée au fil de la journée.",
        "energy": "La consommation est cohérente avec les séquences de fonctionnement observées.",
        "explanations": "Les faits, observations et hypothèses restent distingués.",
        "shutters_advice": "La position des volets est décrite sans lui attribuer seule un effet causal.",
        "ventilation_advice": "Aucune conclusion n'est tirée de la seule humidité relative.",
        "daikin_advice": "Le fonctionnement est cohérent avec le suivi des consignes observées.",
        "outlook": "Journée historique : aucune projection future n'est inventée.",
        "vigilance": "Aucun point de vigilance significatif.",
        "conclusion": "Journée thermiquement maîtrisée.",
    }


def test_day_without_year_defaults_to_current_local_year_and_requires_expert_publication():
    async def scenario():
        fixed_now = datetime.fromisoformat("2026-08-30T21:00:00+02:00")
        service = RecordingService()
        async with _session_for(service, lambda: fixed_now) as session:
            await session.initialize()
            result = await session.call_tool(
                "AnalyseThermique",
                {"mode": "relative_day", "day": "20-08"},
            )
        return service, result

    service, result = asyncio.run(scenario())
    assert result.isError is False
    start, end, compare = service.calls[0]
    assert start == datetime.fromisoformat("2026-08-20T00:00:00+02:00")
    assert end == datetime.fromisoformat("2026-08-21T00:00:00+02:00")
    assert compare is None
    structured = result.structuredContent
    assert structured["date_resolution"]["resolved_date"] == "2026-08-20"
    assert structured["date_resolution"]["year_source"] == "current_year_default"
    assert structured["expertise_day"]["profile"] == "day"
    assert structured["expert_report_publication"]["required"] is True
    assert structured["expert_report_publication"]["profile"] == "day"
    assert structured["interaction_context"]["voice_request_alias"] == "Analyse jour"


def test_explicit_older_year_is_respected_and_today_runs_only_to_now():
    async def scenario():
        fixed_now = datetime.fromisoformat("2026-08-30T21:00:00+02:00")
        service = RecordingService()
        async with _session_for(service, lambda: fixed_now) as session:
            await session.initialize()
            older = await session.call_tool(
                "AnalyseThermique",
                {"mode": "relative_day", "day": "20-08-2025"},
            )
            today = await session.call_tool(
                "AnalyseThermique",
                {"mode": "relative_day", "day": "today"},
            )
        return service, older, today

    service, older, today = asyncio.run(scenario())
    assert older.isError is False
    assert today.isError is False
    assert service.calls[0][0] == datetime.fromisoformat("2025-08-20T00:00:00+02:00")
    assert service.calls[0][1] == datetime.fromisoformat("2025-08-21T00:00:00+02:00")
    assert older.structuredContent["date_resolution"]["year_source"] == "explicit"
    assert service.calls[1][0] == datetime.fromisoformat("2026-08-30T00:00:00+02:00")
    assert service.calls[1][1] == datetime.fromisoformat("2026-08-30T21:00:00+02:00")
    assert today.structuredContent["date_resolution"]["completeness"] == "today_so_far"


def test_intraday_window_keeps_existing_relative_day_behavior_without_forcing_day_report():
    async def scenario():
        fixed_now = datetime.fromisoformat("2026-08-30T21:00:00+02:00")
        service = RecordingService()
        async with _session_for(service, lambda: fixed_now) as session:
            await session.initialize()
            result = await session.call_tool(
                "AnalyseThermique",
                {
                    "mode": "relative_day",
                    "day": "20-08",
                    "start_time": "13:00",
                    "end_time": "17:00",
                },
            )
        return service, result

    service, result = asyncio.run(scenario())
    assert result.isError is False
    assert service.calls[0][0] == datetime.fromisoformat("2026-08-20T13:00:00+02:00")
    assert service.calls[0][1] == datetime.fromisoformat("2026-08-20T17:00:00+02:00")
    assert result.structuredContent["date_resolution"]["full_day_profile"] is False
    assert result.structuredContent["expert_report_publication"]["required"] is False
    assert "expertise_day" not in result.structuredContent


def test_day_expertise_is_published_to_same_persistent_notification_and_detail_reuses_it():
    async def scenario():
        fixed_now = datetime.fromisoformat("2026-08-30T21:00:00+02:00")
        service = RecordingService()
        publisher = RecordingPublisher()
        async with _session_for(service, lambda: fixed_now, publisher) as session:
            await session.initialize()
            analysed = await session.call_tool(
                "AnalyseThermique",
                {"mode": "relative_day", "day": "20-08"},
            )
            analysis_id = analysed.structuredContent["analysis_id"]
            published = await session.call_tool(
                "PublierRapportThermique",
                _day_report_payload(analysis_id),
            )
            detail = await session.call_tool("DernierRapportThermique", {})
        return publisher, analysed, published, detail

    publisher, analysed, published, detail = asyncio.run(scenario())
    assert analysed.isError is False
    assert published.isError is False
    assert detail.isError is False
    assert len(publisher.calls) == 1
    assert publisher.calls[0]["profile"] == "day"
    assert "## 🌡️ Consignes et suivi" in published.structuredContent["full_report"]
    assert published.structuredContent["profile"] == "day"
    assert detail.structuredContent["profile"] == "day"
    assert detail.structuredContent["full_report"] == published.structuredContent["full_report"]
    assert detail.structuredContent["recalculation"] is False
    assert detail.structuredContent["new_expertise"] is False
    assert detail.structuredContent["new_notification"] is False


def test_future_day_is_rejected_before_service_call():
    async def scenario():
        fixed_now = datetime.fromisoformat("2026-08-30T21:00:00+02:00")
        service = RecordingService()
        async with _session_for(service, lambda: fixed_now) as session:
            await session.initialize()
            result = await session.call_tool(
                "AnalyseThermique",
                {"mode": "relative_day", "day": "31-12"},
            )
        return service, result

    service, result = asyncio.run(scenario())
    assert result.isError is True
    assert "future thermal days cannot be analysed" in result.content[0].text
    assert service.calls == []
