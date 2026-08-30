from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app.google_sheets_source import _row_to_sample
from app.models import ThermalSample
from app.service import _life_state_context


def _sample(ts, awake):
    return ThermalSample(
        ts=ts,
        temp_indoor=21.0,
        humidity_indoor=50.0,
        temp_outdoor_ref=18.0,
        humidity_outdoor=60.0,
        setpoint=21.0,
        hvac_mode="cool",
        hvac_action="cooling",
        compressor_frequency=15.0,
        compressor_energy_day=1.0,
        cool_energy_last_hour=None,
        heat_energy_last_hour=None,
        lux=1000.0,
        sun_elevation=20.0,
        sun_azimuth=100.0,
        shutter_salon=50.0,
        shutter_terrasse=50.0,
        window_open=False,
        door_window_open=False,
        awake=awake,
    )


def test_sheet_parser_reads_prise_de_comptage():
    tz = ZoneInfo("Europe/Paris")
    row = {
        "Horodateur_ISO": "2026-08-30T22:00:00+02:00",
        "Prise_de_comptage": "off",
    }
    sample = _row_to_sample(row, tz)
    assert sample is not None
    assert sample.awake is False


def test_life_state_context_keeps_sleep_awake_and_unknown_distinct():
    start = datetime(2026, 8, 30, 22, 0, tzinfo=ZoneInfo("Europe/Paris"))
    samples = [
        _sample(start, True),
        _sample(start + timedelta(minutes=5), False),
        _sample(start + timedelta(minutes=10), None),
        _sample(start + timedelta(minutes=15), None),
    ]
    context = _life_state_context(samples)
    assert context["awake_minutes"] == 5.0
    assert context["asleep_minutes"] == 5.0
    assert context["unknown_minutes"] == 5.0
    assert context["dominant_state"] == "mixed"
    assert context["transitions"] == 1
    assert context["coverage"] == 0.667
