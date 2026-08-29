from __future__ import annotations

import os
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from .data_source import InMemoryDataSource
from .google_sheets_source import GoogleSheetsDataSource
from .natural_periods import resolve_natural_period
from .service import ThermalAnalysisService


APP_VERSION = "0.1.0-dev.3"


def _build_source():
    service_account_file = os.getenv("THERMAL_GOOGLE_SERVICE_ACCOUNT_FILE")
    spreadsheet_id = os.getenv("THERMAL_SPREADSHEET_ID")
    worksheet_name = os.getenv("THERMAL_WORKSHEET_NAME", "Confort thermique")
    timezone = os.getenv("THERMAL_TIMEZONE", "Europe/Paris")

    if service_account_file and spreadsheet_id:
        return GoogleSheetsDataSource(
            service_account_file=service_account_file,
            spreadsheet_id=spreadsheet_id,
            worksheet_name=worksheet_name,
            timezone=timezone,
        )
    return InMemoryDataSource([])


app = FastAPI(title="Maison Élise — Analyse thermique", version=APP_VERSION)
source = _build_source()
service = ThermalAnalysisService(source)


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


@app.post("/analyse")
def analyse(body: AnalyseBody):
    try:
        return service.analyse(body.start, body.end, body.compare)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/analyse/natural")
def analyse_natural(body: NaturalAnalyseBody):
    try:
        timezone = os.getenv("THERMAL_TIMEZONE", "Europe/Paris")
        now = datetime.now(ZoneInfo(timezone))
        start, end = resolve_natural_period(body.period, now, timezone)
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
