from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app.compressor_regime import (
    classify_compressor_frequency,
    compressor_regime_durations,
)
from app.metier_context import METIER_CONTEXT, METIER_CONTEXT_VERSION
from app.models import ThermalSample


def _sample(ts, hz):
    return ThermalSample(
        ts=ts,
        temp_indoor=21.0,
        humidity_indoor=50.0,
        temp_outdoor_ref=18.0,
        humidity_outdoor=60.0,
        setpoint=21.0,
        hvac_mode="cool",
        hvac_action="cooling",
        compressor_frequency=hz,
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
    )


def test_compressor_regime_boundaries_include_stopped():
    assert classify_compressor_frequency(0) == "arrêté"
    assert classify_compressor_frequency(15) == "très faible"
    assert classify_compressor_frequency(16) == "faible"
    assert classify_compressor_frequency(22) == "faible"
    assert classify_compressor_frequency(23) == "moyen"
    assert classify_compressor_frequency(35) == "moyen"
    assert classify_compressor_frequency(36) == "fort"
    assert classify_compressor_frequency(None) is None


def test_compressor_regime_durations_keep_missing_frequency_unknown():
    start = datetime(2026, 8, 31, 0, 0, tzinfo=ZoneInfo("Europe/Paris"))
    samples = [
        _sample(start, 0),
        _sample(start + timedelta(minutes=5), 12),
        _sample(start + timedelta(minutes=10), 18),
        _sample(start + timedelta(minutes=15), 30),
        _sample(start + timedelta(minutes=20), 40),
        _sample(start + timedelta(minutes=25), None),
        _sample(start + timedelta(minutes=30), None),
    ]

    result = compressor_regime_durations(samples)
    assert result["minutes"] == {
        "arrêté": 5.0,
        "très faible": 5.0,
        "faible": 5.0,
        "moyen": 5.0,
        "fort": 5.0,
    }
    assert result["known_minutes"] == 25.0
    assert result["unknown_minutes"] == 5.0
    assert result["coverage"] == 0.833


def test_metier_context_v11_matches_current_architecture():
    assert METIER_CONTEXT_VERSION == "V1.1"
    assert METIER_CONTEXT["source"].startswith("referentiel_metier_clim.txt V1.1")
    assert METIER_CONTEXT["life_state"]["source"] == "historical_sheet_column_Prise_de_comptage"
    assert METIER_CONTEXT["life_state"]["unknown"] == "do_not_infer"
    assert METIER_CONTEXT["daikin"]["power_w_rule"] == "instantaneous_W_values_are_not_used_for_current_thermal_expertise"
    assert METIER_CONTEXT["setpoint"]["wording"] == "écart à la consigne / écart moyen à la consigne"


def test_day_report_requests_detailed_compressor_solicitation():
    rule = METIER_CONTEXT["reporting"]["day_compressor_solicitation"]
    assert "stopped_very_low_low_medium_and_high_minutes" in rule
    assert "unknown_minutes_if_nonzero" in rule
    assert "do_not_replace_this_detail_with_only_one_average" in rule
