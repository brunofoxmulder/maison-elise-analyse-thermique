from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import FastAPI
from pydantic import BaseModel

from .config import AnalysisConfig
from .google_sheets_source import GoogleSheetsDataSource
from .mcp_server import build_mcp_server
from .natural_language import parse_natural_request
from .notification_publisher import HomeAssistantNotificationPublisher
from .service import ThermalAnalysisService
from .weather_forecast import HomeAssistantWeatherForecastProvider


APP_VERSION = "0.1.0-dev.16"
APP_TIMEZONE = os.getenv("THERMAL_TIMEZONE", "Europe/Paris")


class AnalyseBody(BaseModel):
    start: str
    end: str
    compare: str | None = None


class NaturalAnalyseBody(BaseModel):
    request: str


def _required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def _build_service() -> ThermalAnalysisService:
    service_account_file = _required_env("SERVICE_ACCOUNT_FILE")
    spreadsheet_id = _required_env("SPREADSHEET_ID")
    worksheet_name = os.getenv("WORKSHEET_NAME", "Confort thermique")
    weather_entity = os.getenv("WEATHER_ENTITY", "").strip()

    source = GoogleSheetsDataSource(
        service_account_file=Path(service_account_file),
        spreadsheet_id=spreadsheet_id,
        worksheet_name=worksheet_name,
        timezone=APP_TIMEZONE,
    )
    forecast_provider = HomeAssistantWeatherForecastProvider(
        weather_entity=weather_entity,
        timezone=APP_TIMEZONE,
    )
    return ThermalAnalysisService(
        source,
        AnalysisConfig(),
        forecast_provider=forecast_provider,
    )


def _build_notification_publisher():
    notification_service = os.getenv("NOTIFICATION_SERVICE", "").strip()
    mail_entity = os.getenv("MAIL_ENTITY", "").strip()
    return HomeAssistantNotificationPublisher(
        notification_service=notification_service,
        mail_entity=mail_entity,
    )


service = _build_service()
notification_publisher = _build_notification_publisher()
mcp_server = build_mcp_server(
    service,
    timezone=APP_TIMEZONE,
    notification_publisher=notification_publisher,
)

app = FastAPI(title="Maison Élise — Analyse thermique", version=APP_VERSION)


@app.get("/health")
def health():
    return {
        "status": "ok",
        "app": "Maison Élise — Analyse thermique",
        "version": APP_VERSION,
        "timezone": APP_TIMEZONE,
        "mcp_endpoint": "/mcp",
    }


@app.get("/diagnostic")
def diagnostic():
    return {
        "status": "ok",
        "app": "Maison Élise — Analyse thermique",
        "version": APP_VERSION,
        "timezone": APP_TIMEZONE,
        "mcp": {
            "transport": "streamable-http",
            "endpoint": "/mcp",
            "stateless_http": True,
            "json_response": True,
        },
        "source": {
            "spreadsheet_id_configured": bool(os.getenv("SPREADSHEET_ID", "").strip()),
            "worksheet_name": os.getenv("WORKSHEET_NAME", "Confort thermique"),
            "service_account_file": os.getenv("SERVICE_ACCOUNT_FILE", ""),
        },
        "weather": {
            "entity": os.getenv("WEATHER_ENTITY", "").strip(),
        },
        "publication": {
            "notification_service": os.getenv("NOTIFICATION_SERVICE", "").strip(),
            "mail_entity": os.getenv("MAIL_ENTITY", "").strip(),
        },
    }


def _parse_datetime(value: str) -> datetime:
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None or dt.utcoffset() is None:
        dt = dt.replace(tzinfo=ZoneInfo(APP_TIMEZONE))
    return dt


@app.post("/analyse")
def analyse(body: AnalyseBody):
    start = _parse_datetime(body.start)
    end = _parse_datetime(body.end)
    return service.analyse(start, end, compare=body.compare)


@app.post("/analyse/natural")
def analyse_natural(body: NaturalAnalyseBody):
    parsed = parse_natural_request(body.request, timezone=APP_TIMEZONE)
    result = service.analyse(parsed.start, parsed.end, compare=parsed.compare)
    result["resolved_request"] = {
        "start": parsed.start.isoformat(),
        "end": parsed.end.isoformat(),
        "compare": parsed.compare,
        "source": "natural_language_parser",
    }
    return result


# Keep the legacy HTTP routes above this catch-all mount so their paths remain
# unchanged, while FastMCP serves its default Streamable HTTP endpoint at /mcp.
app.mount("/", mcp_server.streamable_http_app())
