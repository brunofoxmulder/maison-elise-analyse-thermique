from __future__ import annotations

from copy import deepcopy
import json
from datetime import datetime, time, timedelta
import re
from typing import Literal
from zoneinfo import ZoneInfo

from mcp.server.fastmcp import FastMCP
from mcp.types import CallToolResult, TextContent

from .diagnostics import (
    record_error,
    record_request,
    record_resolution,
    record_result,
)
from .notification_publisher import UnavailableNotificationPublisher
from .service import ThermalAnalysisService


AnalysisMode = Literal["current_h2", "relative_day", "explicit", "last_result"]
RelativeDay = Literal["today", "yesterday"]
CompareMode = Literal[
    "previous_period",
    "previous_hour",
    "previous_day",
    "j-1",
    "previous_week",
    "s-1",
    "previous_month",
    "m-1",
]

_TIME_RE = re.compile(r"^(?P<hour>\d{1,2})(?::(?P<minute>\d{2}))?$")


def _parse_clock(value: str, field_name: str) -> time:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} is required when mode=relative_day")
    match = _TIME_RE.fullmatch(value.strip())
    if not match:
        raise ValueError(f"{field_name} must use HH:MM or HH")
    hour = int(match.group("hour"))
    minute = int(match.group("minute") or 0)
    if hour > 23 or minute > 59:
        raise ValueError(f"{field_name} is not a valid local time")
    return time(hour=hour, minute=minute)


def _normalize_now(now_value: datetime, tz: ZoneInfo) -> datetime:
    if now_value.tzinfo is None or now_value.utcoffset() is None:
        return now_value.replace(tzinfo=tz)
    return now_value.astimezone(tz)


def _relative_day_period(
    now_value: datetime,
    tz: ZoneInfo,
    day: RelativeDay | None,
    start_time: str | None,
    end_time: str | None,
) -> tuple[datetime, datetime]:
    if day not in ("today", "yesterday"):
        raise ValueError("day is required when mode=relative_day")
    local_now = _normalize_now(now_value, tz)
    target_date = local_now.date() - timedelta(days=1 if day == "yesterday" else 0)
    start_clock = _parse_clock(start_time, "start_time")
    end_clock = _parse_clock(end_time, "end_time")
    start = datetime.combine(target_date, start_clock, tzinfo=tz)
    end = datetime.combine(target_date, end_clock, tzinfo=tz)
    if end <= start:
        raise ValueError("end_time must be after start_time on the selected day")
    return start, end


def _normalize_compare(
    compare: CompareMode | None,
    start: datetime,
    end: datetime,
) -> str | None:
    if compare != "previous_hour":
        return compare
    duration_minutes = (end - start).total_seconds() / 60.0
    if not 55.0 <= duration_minutes <= 65.0:
        raise ValueError(
            "previous_hour is only valid for an explicit or relative period of about one hour"
        )
    return "previous_period"


def _tool_result(result: dict) -> CallToolResult:
    return CallToolResult(
        content=[
            TextContent(
                type="text",
                text=json.dumps(result, ensure_ascii=False, separators=(",", ":")),
            )
        ],
        structuredContent=result,
    )


def build_mcp_server(
    service: ThermalAnalysisService,
    timezone: str = "Europe/Paris",
    now_provider=None,
    notification_publisher=None,
) -> FastMCP:
    """Build the MCP facade around the deterministic thermal service."""
    tz = ZoneInfo(timezone)
    if now_provider is None:
        now_provider = lambda: datetime.now(tz)
    if notification_publisher is None:
        notification_publisher = UnavailableNotificationPublisher()

    last_result: dict | None = None

    mcp = FastMCP(
        name="Maison Élise — Analyse thermique",
        instructions=(
            "Serveur d'analyse thermique déterministe. "
            "Le client choisit le type de période et interprète le JSON sans recalculer les chiffres."
        ),
        host="0.0.0.0",
        stateless_http=True,
        json_response=True,
    )

    @mcp.tool(
        name="AnalyseThermique",
        description=(
            "Analyse thermique déterministe. Pour la demande naturelle 'Analyse heure', 'analyse de l'heure', "
            "'analyse actuelle' ou équivalent, utiliser mode=current_h2 : l'App résout elle-même les deux dernières "
            "heures avec son horloge Europe/Paris ; ne jamais calculer start/end côté LLM. "
            "Pour 'aujourd'hui entre 13 h et 17 h' ou 'hier entre 8 h et 15 h', utiliser mode=relative_day avec "
            "day=today|yesterday et start_time/end_time ; l'App résout elle-même la date locale. "
            "Pour une date historique absolue, utiliser mode=explicit avec start/end ISO 8601 avec fuseau. "
            "Après une analyse, si l'utilisateur dit 'donne-moi le détail', privilégier le résultat déjà présent dans "
            "la conversation ; si un nouvel appel tool est nécessaire, utiliser mode=last_result afin de réutiliser "
            "exactement la dernière analyse sans recalcul ni nouvelle notification. "
            "Pour une réponse vocale normale, faire seulement quelques phrases dans cet ordre : constat, analyse prudente, "
            "préconisation, à venir. Ne pas afficher de titres Markdown, ne pas citer H-2/current_h2 ni les noms internes. "
            "Le détail est destiné à la notification automatique et au suivi vocal sur demande. "
            "Quand expertise_h2 est présent, last_hour est le sujet principal et previous_hour la référence. "
            "Les chiffres déterministes sont la source de vérité : ne pas les recalculer. Suivre analysis_contract et "
            "toutes les interpretation_rule du JSON. Distinguer Fait / Observation / Hypothèse / Incertitude. "
            "Convention volets : 0 %=fermé, 100 %=ouvert ; ne jamais inverser cette convention. "
            "La température Daikin terrasse n'est jamais la météo ni une preuve que le compresseur peine. "
            "Un extérieur plus frais ne signifie jamais automatiquement qu'il faut aérer. "
            "forecast_h4 est le seul horizon prospectif : ne jamais parler de demain ou d'un instant situé après le "
            "dernier point forecast_h4 sauf si l'utilisateur demande explicitement une autre prévision. "
            "Utiliser NORMAL / VIGILANCE / ALERTE seulement si utile à la compréhension, sans alarmisme."
        ),
    )
    def analyse_thermique(
        mode: AnalysisMode,
        start: datetime | None = None,
        end: datetime | None = None,
        compare: CompareMode | None = None,
        day: RelativeDay | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
    ) -> CallToolResult:
        nonlocal last_result

        if mode == "last_result":
            if last_result is None:
                raise ValueError("no previous thermal analysis is cached in this App process")
            reused = deepcopy(last_result)
            reused["interaction_context"] = {
                "reused_previous_analysis": True,
                "fresh_analysis": False,
                "automatic_notification_repeated": False,
            }
            return _tool_result(reused)

        received_start = start
        received_end = end
        received_compare = compare

        if mode == "current_h2":
            resolved_end = _normalize_now(now_provider(), tz)
            resolved_start = resolved_end - timedelta(hours=2)
            resolved_compare = None
        elif mode == "relative_day":
            resolved_start, resolved_end = _relative_day_period(
                now_provider(), tz, day, start_time, end_time
            )
            resolved_compare = _normalize_compare(compare, resolved_start, resolved_end)
        else:
            if start is None or end is None:
                raise ValueError("start and end are required when mode=explicit")
            resolved_start = start
            resolved_end = end
            resolved_compare = _normalize_compare(compare, resolved_start, resolved_end)

        record_resolution(
            mode,
            received_start,
            received_end,
            received_compare,
            resolved_start,
            resolved_end,
            resolved_compare,
        )
        record_request(resolved_start, resolved_end, resolved_compare)
        try:
            result = service.analyse(
                resolved_start,
                resolved_end,
                resolved_compare,
            )
        except Exception as exc:
            record_error(resolved_start, resolved_end, resolved_compare, exc)
            raise

        delivery = notification_publisher.publish(result)
        result["automatic_notification"] = delivery
        result["interaction_context"] = {
            "reused_previous_analysis": False,
            "fresh_analysis": True,
            "detail_follow_up_mode": "last_result",
            "voice_request_alias": "Analyse heure" if mode == "current_h2" else None,
        }
        last_result = deepcopy(result)
        record_result(result)
        return _tool_result(result)

    return mcp
