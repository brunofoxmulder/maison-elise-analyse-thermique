from __future__ import annotations

import json
from datetime import datetime

from mcp.server.fastmcp import FastMCP
from mcp.types import CallToolResult, TextContent

from .service import ThermalAnalysisService


def build_mcp_server(service: ThermalAnalysisService) -> FastMCP:
    """Build the read-only MCP facade around the existing thermal service."""
    mcp = FastMCP(
        name="Maison Élise — Analyse thermique",
        instructions=(
            "Serveur d'analyse thermique déterministe en lecture seule. "
            "Le client choisit une période explicite puis interprète le JSON retourné."
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
            "compare est optionnel et accepte previous_period, previous_day, "
            "previous_week ou previous_month."
        ),
    )
    def analyse_thermique(
        start: datetime,
        end: datetime,
        compare: str | None = None,
    ) -> CallToolResult:
        result = service.analyse(start, end, compare)
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
