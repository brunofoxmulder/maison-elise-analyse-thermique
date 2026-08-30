from datetime import datetime, timedelta

from app.day_interactions import build_opening_interactions
from app.day_profile import build_setpoint_profiles
from app.energy_quality import apply_midnight_cumulative_counter_total
from app.models import ThermalSample


def _sample(
    ts,
    *,
    energy=None,
    window=False,
    door=False,
    outdoor=18.0,
    indoor=21.0,
    humidity_indoor=55.0,
    humidity_outdoor=60.0,
    action="cooling",
    frequency=16.0,
):
    return ThermalSample(
        ts=ts,
        temp_indoor=indoor,
        humidity_indoor=humidity_indoor,
        temp_outdoor_ref=outdoor,
        humidity_outdoor=humidity_outdoor,
        setpoint=21.0,
        hvac_mode="cool",
        hvac_action=action,
        compressor_frequency=frequency,
        compressor_energy_day=energy,
        cool_energy_last_hour=0.2,
        heat_energy_last_hour=0.0,
        lux=0.0,
        sun_elevation=0.0,
        sun_azimuth=0.0,
        shutter_salon=100.0,
        shutter_terrasse=100.0,
        window_open=window,
        door_window_open=door,
    )


def test_midnight_period_uses_latest_fresh_daily_cumulative_counter():
    start = datetime.fromisoformat("2026-08-29T00:00:00+02:00")
    end = datetime.fromisoformat("2026-08-30T00:00:00+02:00")
    samples = [
        _sample(datetime.fromisoformat("2026-08-29T18:55:00+02:00"), energy=5.2),
        _sample(datetime.fromisoformat("2026-08-29T23:55:00+02:00"), energy=6.3),
    ]
    analysis = {
        "compressor_energy": {
            "kwh": 1.1,
            "period_fact_allowed": False,
            "coverage": 0.21,
        }
    }

    apply_midnight_cumulative_counter_total(analysis, samples, start, end)

    energy = analysis["compressor_energy"]
    assert energy["incremental_kwh"] == 1.1
    assert energy["kwh"] == 6.3
    assert energy["period_fact_allowed"] is True
    assert energy["source_rule"] == "daily_cumulative_counter_last_value_from_midnight"
    assert energy["daily_counter_end_lag_minutes"] == 5.0


def test_non_midnight_period_keeps_incremental_energy():
    start = datetime.fromisoformat("2026-08-29T18:55:00+02:00")
    end = datetime.fromisoformat("2026-08-30T00:00:00+02:00")
    samples = [
        _sample(start, energy=5.2),
        _sample(datetime.fromisoformat("2026-08-29T23:55:00+02:00"), energy=6.3),
    ]
    analysis = {"compressor_energy": {"kwh": 1.1, "period_fact_allowed": True}}

    apply_midnight_cumulative_counter_total(analysis, samples, start, end)

    assert analysis["compressor_energy"]["kwh"] == 1.1
    assert "source_rule" not in analysis["compressor_energy"]


def test_opening_interactions_report_context_without_claiming_influence():
    start = datetime.fromisoformat("2026-08-29T08:00:00+02:00")
    samples = [
        _sample(start, window=True, outdoor=18.0, indoor=21.0, action="cooling"),
        _sample(start + timedelta(minutes=5), window=True, outdoor=18.2, indoor=20.9, action="cooling"),
        _sample(start + timedelta(minutes=10), window=False, outdoor=18.4, indoor=20.8, action="cooling"),
        _sample(start + timedelta(minutes=15), window=False, outdoor=18.5, indoor=20.8, action="idle"),
    ]

    interactions = build_opening_interactions(samples)
    window = interactions["window"]

    assert window["open_minutes"] == 10.0
    assert window["cooling_while_open_minutes"] == 10.0
    assert window["outdoor_cooler_while_open_minutes"] == 10.0
    assert len(window["segments"]) == 1
    assert interactions["influence_assessment"] == "not_established_by_this_profile"
    assert interactions["counterfactual_recommendation"] == "not_allowed_without_validated_historical_evidence"
    assert "no_airflow_sensor" in interactions["airflow_rule"]


def test_long_day_profile_exposes_opening_context_and_guardrails_but_h2_does_not():
    start = datetime.fromisoformat("2026-08-29T00:00:00+02:00")
    day_samples = [
        _sample(start + timedelta(minutes=5 * index), window=index in {20, 21})
        for index in range(49)
    ]
    day_profile = build_setpoint_profiles(day_samples)
    assert "opening_interactions" in day_profile
    assert "day_expertise_guardrails" in day_profile
    assert "should_have_opened" in day_profile["day_expertise_guardrails"]["counterfactual_rule"]

    h2_samples = [
        _sample(start + timedelta(minutes=5 * index))
        for index in range(25)
    ]
    h2_profile = build_setpoint_profiles(h2_samples)
    assert "opening_interactions" not in h2_profile
    assert "day_expertise_guardrails" not in h2_profile
