from __future__ import annotations

from contextlib import asynccontextmanager
from html import escape
import os
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from .data_source import InMemoryDataSource
from .diagnostics import diagnostics_text
from .google_sheets_source import GoogleSheetsDataSource
from .mcp_server import build_mcp_server
from .natural_periods import resolve_natural_period
from .notification_publisher import (
    HomeAssistantNotificationPublisher,
    UnavailableNotificationPublisher,
)
from .service import ThermalAnalysisService
from .weather_forecast import (
    HomeAssistantWeatherForecastProvider,
    UnavailableWeatherForecastProvider,
)


APP_VERSION = "0.1.0-dev.13"
APP_TIMEZONE = os.getenv("THERMAL_TIMEZONE", "Europe/Paris")


def _build_source():
    service_account_file = os.getenv("THERMAL_GOOGLE_SERVICE_ACCOUNT_FILE")
    spreadsheet_id = os.getenv("THERMAL_SPREADSHEET_ID")
    worksheet_name = os.getenv("THERMAL_WORKSHEET_NAME", "Confort thermique")

    if service_account_file and spreadsheet_id:
        return GoogleSheetsDataSource(
            service_account_file=service_account_file,
            spreadsheet_id=spreadsheet_id,
            worksheet_name=worksheet_name,
            timezone=APP_TIMEZONE,
        )
    return InMemoryDataSource([])


def _build_forecast_provider():
    token = os.getenv("SUPERVISOR_TOKEN")
    weather_entity = os.getenv("THERMAL_WEATHER_ENTITY", "weather.dammarie_les_lys")
    if not token:
        return UnavailableWeatherForecastProvider("supervisor_token_unavailable")
    try:
        return HomeAssistantWeatherForecastProvider(
            token=token,
            entity_id=weather_entity,
        )
    except ValueError:
        return UnavailableWeatherForecastProvider("invalid_weather_configuration")


def _build_notification_publisher():
    token = os.getenv("SUPERVISOR_TOKEN")
    if not token:
        return UnavailableNotificationPublisher("supervisor_token_unavailable")
    try:
        return HomeAssistantNotificationPublisher(token=token)
    except ValueError:
        return UnavailableNotificationPublisher("invalid_notification_configuration")


source = _build_source()
forecast_provider = _build_forecast_provider()
notification_publisher = _build_notification_publisher()
service = ThermalAnalysisService(source, forecast_provider=forecast_provider)
mcp_server = build_mcp_server(
    service,
    timezone=APP_TIMEZONE,
    notification_publisher=notification_publisher,
)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    async with mcp_server.session_manager.run():
        yield


app = FastAPI(
    title="Maison Élise — Analyse thermique",
    version=APP_VERSION,
    lifespan=lifespan,
)


class AnalyseBody(BaseModel):
    start: datetime
    end: datetime
    compare: str | None = None


class NaturalAnalyseBody(BaseModel):
    period: str
    compare: str | None = None


@app.get("/health")
def health():
    return {
        "status": "ok",
        "version": APP_VERSION,
        "read_only": True,
        "data_source": type(source).__name__,
    }


@app.get("/diagnostic", response_class=HTMLResponse)
def diagnostic():
    text = diagnostics_text()
    safe_text = escape(text)
    data_source = escape(type(source).__name__)
    return HTMLResponse(
        f"""<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Maison Élise — Diagnostic MCP</title>
<style>
body {{ font-family: sans-serif; margin: 20px; background: #111; color: #eee; }}
button {{ font-size: 1rem; padding: 12px 16px; margin: 8px 0 16px; }}
pre {{ white-space: pre-wrap; overflow-wrap: anywhere; background: #000; padding: 12px; border-radius: 8px; }}
#copy-status {{ margin-left: 8px; }}
</style>
</head>
<body>
<h2>Maison Élise — Analyse thermique</h2>
<p>Version {APP_VERSION} · données thermiques en lecture seule · {data_source}</p>
<button type="button" onclick="copyDiagnostic()">Copier le diagnostic</button>
<span id="copy-status" aria-live="polite"></span>
<pre id="diag">{safe_text}</pre>
<script>
async function copyDiagnostic() {{
  const text = document.getElementById('diag').innerText;
  const status = document.getElementById('copy-status');
  try {{
    if (navigator.clipboard && navigator.clipboard.writeText) {{
      await navigator.clipboard.writeText(text);
    }} else {{
      const area = document.createElement('textarea');
      area.value = text;
      area.style.position = 'fixed';
      area.style.opacity = '0';
      document.body.appendChild(area);
      area.focus();
      area.select();
      if (!document.execCommand('copy')) throw new Error('copy failed');
      document.body.removeChild(area);
    }}
    status.textContent = 'Copié';
  }} catch (err) {{
    status.textContent = 'Copie impossible : sélectionne le texte ci-dessous.';
  }}
}}
</script>
</body>
</html>"""
    )


@app.post("/analyse")
def analyse(body: AnalyseBody):
    try:
        return service.analyse(body.start, body.end, body.compare)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/analyse/natural")
def analyse_natural(body: NaturalAnalyseBody):
    try:
        now = datetime.now(ZoneInfo(APP_TIMEZONE))
        start, end = resolve_natural_period(body.period, now, APP_TIMEZONE)
        result = service.analyse(start, end, body.compare)
        result["period_request"] = {
            "text": body.period,
            "resolved_start": start.isoformat(),
            "resolved_end": end.isoformat(),
            "resolver": "deterministic_fr_v1",
        }
        return result
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


# Keep the legacy HTTP routes above this catch-all mount so their paths remain
# unchanged, while FastMCP serves its default Streamable HTTP endpoint at /mcp.
app.mount("/", mcp_server.streamable_http_app())
