from __future__ import annotations

import json
from datetime import datetime, timedelta
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
from .service import ThermalAnalysisService


AnalysisMode = Literal["current_h2", "explicit"]
CompareMode = Literal[
    "previous_period",
    "previous_day",
    "j-1",
    "previous_week",
    "s-1",
    "previous_month",
    "m-1",
]


def build_mcp_server(
    service: ThermalAnalysisService,
    timezone: str = "Europe/Paris",
    now_provider=None,
) -> FastMCP:
    """Build the read-only MCP facade around the existing thermal service."""
    tz = ZoneInfo(timezone)
    if now_provider is None:
        now_provider = lambda: datetime.now(tz)

    mcp = FastMCP(
        name="Maison Élise — Analyse thermique",
        instructions=(
            "Serveur d'analyse thermique déterministe en lecture seule. "
            "Le client choisit le type de période et interprète le JSON sans recalculer les chiffres. "
            "Pour un diagnostic H-2 actuel, choisir mode=current_h2 : l'App résout elle-même l'horloge locale."
        ),
        host="0.0.0.0",
        stateless_http=True,
        json_response=True,
    )

    @mcp.tool(
        name="AnalyseThermique",
        description=(
            "Analyse thermique déterministe en lecture seule. Le paramètre mode est obligatoire. "
            "Pour toute demande actuelle du type H-2, dernières heures, maintenant ou ce qui vient de se passer, "
            "utiliser OBLIGATOIREMENT mode=current_h2 et ne pas calculer de date/heure : l'App prend maintenant "
            "dans son fuseau configuré et construit les deux dernières heures. En mode=current_h2, start, end et compare "
            "sont ignorés même s'ils sont fournis. Pour une période historique ou calendaire explicite, utiliser "
            "mode=explicit avec start et end ISO 8601 avec fuseau ; compare est optionnel et limité aux valeurs du schéma. "
            "Quand expertise_h2 est présent, baser la réponse sur expertise_h2 : last_hour est le sujet principal, "
            "previous_hour la référence ; le top-level analysis est seulement l'agrégat historique des deux heures. "
            "Les chiffres déterministes sont la source de vérité : ne pas les recalculer. Suivre analysis_contract et "
            "toutes les interpretation_rule du JSON. Distinguer Fait / Observation / Hypothèse / Incertitude. "
            "La température Daikin terrasse n'est jamais la météo ni une preuve que le compresseur peine. "
            "Un extérieur plus frais ne signifie jamais automatiquement qu'il faut aérer : considérer aussi l'humidité, "
            "les ouvrants et le fonctionnement Daikin. forecast_h4 est prospectif, jamais certain. "
            "Pour une réponse Assist normale : rester concise, utiliser NORMAL / VIGILANCE / ALERTE et conseiller "
            "Volets / Aération / Daikin."
        ),
    )
    def analyse_thermique(
        mode: AnalysisMode,
        start: datetime | None = None,
        end: datetime | None = None,
        compare: CompareMode | None = None,
    ) -> CallToolResult:
        received_start = start
        received_end = end
        received_compare = compare

        if mode == "current_h2":
            resolved_end = now_provider()
            if resolved_end.tzinfo is None or resolved_end.utcoffset() is None:
                resolved_end = resolved_end.replace(tzinfo=tz)
            else:
                resolved_end = resolved_end.astimezone(tz)
            resolved_start = resolved_end - timedelta(hours=2)
            resolved_compare = None
        else:
            if start is None or end is None:
                raise ValueError("start and end are required when mode=explicit")
            resolved_start = start
            resolved_end = end
            resolved_compare = compare

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
        record_result(result)
        return CallToolResult(
            content=[
                TextContent(
                    type="text",
                    text=json.dumps(result, ensure_ascii=False, separators=(",", ":")),
                )
            ],
            structuredContent=result,
        )

    return mcp
