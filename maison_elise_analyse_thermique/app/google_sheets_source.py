from __future__ import annotations

import time
from datetime import datetime
from zoneinfo import ZoneInfo

import gspread

from .data_source import DataSource
from .models import ThermalSample


def _float(value):
    if value in (None, "", "unknown", "unavailable", "none", "null"):
        return None
    try:
        return float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return None


def _bool(value):
    if value is None or value == "":
        return None
    text = str(value).strip().lower()
    if text in {"on", "open", "true", "1"}:
        return True
    if text in {"off", "closed", "false", "0"}:
        return False
    return None


def _timestamp(value, tz: ZoneInfo):
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=tz)


def _require_aware_bounds(start: datetime, end: datetime) -> None:
    if start.tzinfo is None or start.utcoffset() is None:
        raise ValueError("start must be timezone-aware")
    if end.tzinfo is None or end.utcoffset() is None:
        raise ValueError("end must be timezone-aware")


def _row_to_sample(row, tz: ZoneInfo) -> ThermalSample | None:
    ts = _timestamp(row.get("Horodateur_ISO"), tz)
    if ts is None:
        return None
    return ThermalSample(
        ts=ts,
        temp_indoor=_float(row.get("Température_salon")),
        humidity_indoor=_float(row.get("Humidité_salon")),
        temp_outdoor_ref=_float(row.get("Température_extérieure_fiable")),
        humidity_outdoor=_float(row.get("Humidité_extérieure")),
        setpoint=_float(row.get("Consigne")),
        hvac_mode=(row.get("HVAC_mode") or None),
        hvac_action=(row.get("HVAC_action") or None),
        compressor_frequency=_float(row.get("Frequence_compresseur")),
        compressor_energy_day=_float(row.get("Energie_compresseur_jour")),
        cool_energy_last_hour=_float(row.get("Cool_energy_derniere_heure")),
        heat_energy_last_hour=_float(row.get("Heat_energy_derniere_heure")),
        lux=_float(row.get("Lux")),
        sun_elevation=_float(row.get("Élévation_solaire")),
        sun_azimuth=_float(row.get("Azimut_solaire")),
        shutter_salon=_float(row.get("Volet_salon")),
        shutter_terrasse=_float(row.get("Volet_terrasse")),
        window_open=_bool(row.get("Fenêtre_salon")),
        door_window_open=_bool(row.get("Porte_fenêtre")),
        temp_outdoor_daikin=_float(row.get("Température_extérieure_Daikin")),
    )


class GoogleSheetsDataSource(DataSource):
    def __init__(self, service_account_file: str, spreadsheet_id: str, worksheet_name: str = "Confort thermique", timezone: str = "Europe/Paris", cache_ttl_seconds: float = 30.0):
        self.client = gspread.service_account(filename=service_account_file)
        self.worksheet = self.client.open_by_key(spreadsheet_id).worksheet(worksheet_name)
        self.tz = ZoneInfo(timezone)
        self.cache_ttl_seconds = max(0.0, float(cache_ttl_seconds))
        self._cached_samples = None
        self._cached_at = None

    def _samples_snapshot(self) -> list[ThermalSample]:
        now = time.monotonic()
        if self._cached_samples is not None and self._cached_at is not None and now - self._cached_at <= self.cache_ttl_seconds:
            return self._cached_samples
        # Keep formatted values as strings. gspread's default numericise() treats
        # commas as thousands separators, so French decimals such as "19,3"
        # would otherwise become 193 before our locale-aware _float() parser.
        rows = self.worksheet.get_all_records(
            default_blank="",
            numericise_ignore=["all"],
        )
        samples = [sample for row in rows if (sample := _row_to_sample(row, self.tz)) is not None]
        samples.sort(key=lambda sample: sample.ts)
        self._cached_samples = samples
        self._cached_at = now
        return samples

    def load(self, start: datetime, end: datetime) -> list[ThermalSample]:
        _require_aware_bounds(start, end)
        return [sample for sample in self._samples_snapshot() if start <= sample.ts < end]
