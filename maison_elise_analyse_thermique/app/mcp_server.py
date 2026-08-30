from __future__ import annotations

import json
from datetime import datetime

from mcp.server.fastmcp import FastMCP
from mcp.types import CallToolResult, TextContent

from .diagnostics import record_error, record_request, record_result
from .service import ThermalAnalysisService


def build_mcp_server(service: ThermalAnalysisService) -> FastMCP:
    """Build the read-only MCP facade around the existing thermal service."""
    mcp = FastMCP(
        name="Maison Élise — Analyse thermique",
        instructions=(
            "Serveur d'analyse thermique déterministe en lecture seule. "
            "Le client choisit la période et interprète le JSON sans recalculer les chiffres. "
            "Pour un diagnostic horaire H-2 courant, demander les deux dernières heures : "
            "expertise_h2.last_hour est le sujet principal et previous_hour la référence immédiate."
        ),
        host="0.0.0.0",
        stateless_http=True,
        json_response=True,
    )

    @mcp.tool(
        name="AnalyseThermique",
        description=(
            "Analyse une période thermique explicite en lecture seule. "
            "start et end doivent être des dates/heures ISO 8601 avec fuseau horaire. "
            "Pour une demande H-2/dernières heures, utiliser start=end-2h et end proche de maintenant. "
            "Quand expertise_h2 est présent, baser la réponse sur expertise_h2 : last_hour est le sujet principal, "
            "previous_hour la référence ; le top-level analysis est seulement l'agrégat historique des deux heures. "
            "Les chiffres déterministes sont la source de vérité : ne pas les recalculer. Suivre analysis_contract et "
            "toutes les interpretation_rule du JSON. Distinguer Fait / Observation / Hypothèse / Incertitude. "
            "La température Daikin terrasse n'est jamais la météo ni une preuve que le compresseur peine. "
            "Un extérieur plus frais ne signifie jamais automatiquement qu'il faut aérer : considérer aussi l'humidité, "
            "les ouvrants et le fonctionnement Daikin. forecast_h4 est prospectif, jamais certain. "
            "Pour une réponse Assist normale : rester concise, utiliser NORMAL / VIGILANCE / ALERTE et conseiller "
            "Volets / Aération / Daikin. compare est optionnel et accepte previous_period, previous_day, previous_week "
            "ou previous_month."
        ),
    )
    def analyse_thermique(
        start: datetime,
        end: datetime,
        compare: str | None = None,
    ) -> CallToolResult:
        record_request(start, end, compare)
        try:
            result = service.analyse(start, end, compare)
        except Exception as exc:
            record_error(start, end, compare, exc)
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
