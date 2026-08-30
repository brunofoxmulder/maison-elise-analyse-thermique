from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.google_sheets_source import GoogleSheetsDataSource, _float
from app.service import ThermalAnalysisService


class FakeWorksheet:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    def get_all_records(self, **kwargs):
        self.calls.append(kwargs)
        return self.rows


class FakeSpreadsheet:
    def __init__(self, worksheet):
        self._worksheet = worksheet

    def worksheet(self, _name):
        return self._worksheet


class FakeClient:
    def __init__(self, worksheet):
        self._worksheet = worksheet

    def open_by_key(self, _spreadsheet_id):
        return FakeSpreadsheet(self._worksheet)


def _rows_for_day(day: int, indoor: str, outdoor: str):
    tz = timezone(timedelta(hours=2))
    start = datetime(2026, 8, day, 0, 0, tzinfo=tz)
    rows = []
    for index in range(288):
        ts = start + timedelta(minutes=5 * index)
        rows.append(
            {
                "Horodateur_ISO": ts.isoformat(),
                "Température_salon": indoor,
                "Température_extérieure_fiable": outdoor,
                "Humidité_salon": "53,0",
                "HVAC_mode": "cool",
                "HVAC_action": "cooling",
                "Fenêtre_salon": "off",
                "Porte_fenêtre": "off",
            }
        )
    return rows


def test_float_parses_french_decimal_comma():
    assert _float("19,3") == pytest.approx(19.3)
    assert _float("16,6") == pytest.approx(16.6)


def test_google_sheet_disables_gspread_numericise(monkeypatch):
    worksheet = FakeWorksheet(_rows_for_day(29, "19,3", "16,6")[:1])
    monkeypatch.setattr(
        "app.google_sheets_source.gspread.service_account",
        lambda filename: FakeClient(worksheet),
    )

    source = GoogleSheetsDataSource("fake.json", "sheet-id")
    tz = timezone(timedelta(hours=2))
    samples = source.load(
        datetime(2026, 8, 29, 0, 0, tzinfo=tz),
        datetime(2026, 8, 30, 0, 0, tzinfo=tz),
    )

    assert worksheet.calls == [
        {"default_blank": "", "numericise_ignore": ["all"]}
    ]
    assert len(samples) == 1
    assert samples[0].temp_indoor == pytest.approx(19.3)
    assert samples[0].temp_outdoor_ref == pytest.approx(16.6)


def test_daily_means_and_previous_day_delta_keep_french_decimals(monkeypatch):
    rows = _rows_for_day(28, "20,59", "18,49") + _rows_for_day(
        29, "20,87", "18,49"
    )
    worksheet = FakeWorksheet(rows)
    monkeypatch.setattr(
        "app.google_sheets_source.gspread.service_account",
        lambda filename: FakeClient(worksheet),
    )

    source = GoogleSheetsDataSource("fake.json", "sheet-id")
    service = ThermalAnalysisService(source)
    tz = timezone(timedelta(hours=2))
    result = service.analyse(
        datetime(2026, 8, 29, 0, 0, tzinfo=tz),
        datetime(2026, 8, 29, 23, 59, 59, tzinfo=tz),
        "previous_day",
    )

    current = result["analysis"]
    reference = result["comparison"]["analysis"]
    delta = result["comparison"]["delta"]

    assert current["temperature_indoor"]["mean"] == pytest.approx(20.87)
    assert current["temperature_outdoor_reference"]["mean"] == pytest.approx(18.49)
    assert reference["temperature_indoor"]["mean"] == pytest.approx(20.59)
    assert reference["temperature_outdoor_reference"]["mean"] == pytest.approx(18.49)
    assert delta["temperature_indoor_mean_delta_c"] == pytest.approx(0.28)
    assert delta["temperature_outdoor_mean_delta_c"] == pytest.approx(0.0)
