from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app.google_sheets_source import _row_to_sample
from app.h2_trend import classify_temperature_evolution
from app.models import ThermalSample
from app.service import ThermalAnalysisService


TZ = ZoneInfo("Europe/Paris")


def _sample(ts, *, indoor, humidity_in, outdoor, humidity_out, setpoint, cool_kwh, daikin):
    return ThermalSample(
        ts=ts,
        temp_indoor=indoor,
        humidity_indoor=humidity_in,
        temp_outdoor_ref=outdoor,
        humidity_outdoor=humidity_out,
        setpoint=setpoint,
        hvac_mode="cool",
        hvac_action="cooling",
        compressor_frequency=24.0,
        compressor_energy_day=4.0 + (ts.hour * 60 + ts.minute) / 10000.0,
        cool_energy_last_hour=cool_kwh,
        heat_energy_last_hour=0.0,
        lux=20000.0,
        sun_elevation=30.0,
        sun_azimuth=100.0,
        shutter_salon=40.0,
        shutter_terrasse=50.0,
        window_open=False,
        door_window_open=False,
        temp_outdoor_daikin=daikin,
    )


class FakeSource:
    def __init__(self, samples):
        self.samples = samples

    def load(self, start, end):
        return [sample for sample in self.samples if start <= sample.ts < end]


def _two_hours():
    start = datetime(2026, 8, 30, 10, 0, tzinfo=TZ)
    samples = []
    for index in range(24):
        ts = start + timedelta(minutes=5 * index)
        last_hour = ts >= start + timedelta(hours=1)
        after_setpoint_change = ts >= start + timedelta(hours=1, minutes=30)
        samples.append(
            _sample(
                ts,
                indoor=(19.4 + 0.02 * index) if not last_hour else (19.65 + 0.07 * (index - 12)),
                humidity_in=60.0 if not last_hour else 58.0,
                outdoor=10.0,
                humidity_out=80.0,
                setpoint=21.0 if after_setpoint_change else 19.0,
                cool_kwh=0.20 if not last_hour else 0.15,
                daikin=17.0,
            )
        )
    return start, start + timedelta(hours=2), samples


def test_google_sheet_maps_daikin_temperature_as_microclimate_context() -> None:
    row = {
        "Horodateur_ISO": "2026-08-30T11:00:00+02:00",
        "Température_salon": "20,1",
        "Humidité_salon": "58",
        "Température_extérieure_fiable": "17,2",
        "Température_extérieure_Daikin": "24,6",
    }
    sample = _row_to_sample(row, TZ)
    assert sample is not None
    assert sample.temp_outdoor_ref == 17.2
    assert sample.temp_outdoor_daikin == 24.6


def test_h2_contract_uses_last_hour_as_primary_and_previous_as_reference() -> None:
    start, end, samples = _two_hours()
    result = ThermalAnalysisService(FakeSource(samples)).analyse(start, end)

    h2 = result["expertise_h2"]
    assert h2["profile"] == "h2_last_hour_vs_previous_hour"
    assert h2["primary_period"]["start"] == "2026-08-30T11:00:00+02:00"
    assert h2["reference_period"]["start"] == "2026-08-30T10:00:00+02:00"
    contract = h2["analysis_contract"]
    assert contract["primary_rule"] == (
        "analyse_the_last_hour_and_compare_it_with_the_previous_hour"
    )
    assert contract["prompt_version"] == "h2-expert-v1"
    assert "top_level_analysis_is_the_legacy_two_hour_aggregate" in contract["h2_result_rule"]
    assert "weaken_the_conclusion_explicitly" in contract["quality_rule"]
    assert "distinguish_fact_observation_hypothesis_and_uncertainty" in contract["evidence_rule"]
    assert "possible_inertia" in contract["setpoint_transition_rule"]
    assert "dehumidification_or_modulation" in contract["dehumidification_rule"]
    assert "cooling_and_heating_modes" in contract["ventilation_context_rule"]
    assert "distinguish_solar_geometry_bright_sky_and_effective_sun" in contract["solar_rule"]
    assert contract["response_contract"]["status_rules"]["ALERTE"].startswith("use_only_for_clearly_abnormal")
    assert "three_or_four_useful_conclusions" in contract["response_contract"]["assist_voice_rule"]

    last = h2["last_hour"]
    previous = h2["previous_hour"]
    assert previous["setpoint_tracking"]["latest_setpoint_c"] == 19.0
    assert last["setpoint_tracking"]["latest_setpoint_c"] == 21.0
    assert last["setpoint_tracking"]["transition_count"] == 1
    assert last["setpoint_tracking"]["transitions"][0]["from_c"] == 19.0
    assert last["setpoint_tracking"]["transitions"][0]["to_c"] == 21.0

    assert h2["comparison"]["active_setpoint_delta_c"] == 2.0
    assert h2["comparison"]["cool_energy_last_hour_observation_delta_kwh"] == -0.05
    assert h2["comparison"]["temperature_evolution_classification"]["source_rule"] == (
        "pyscript_horaire_v5_qualifier_tendance"
    )


def test_h2_air_properties_do_not_treat_relative_humidity_alone_as_ventilation_rule() -> None:
    start, end, samples = _two_hours()
    h2 = ThermalAnalysisService(FakeSource(samples)).analyse(start, end)["expertise_h2"]

    air = h2["last_hour"]["air_properties"]
    indoor_ah = air["indoor_absolute_humidity_g_m3"]["mean"]
    outdoor_ah = air["outdoor_absolute_humidity_g_m3"]["mean"]

    # Malgré 80 % HR dehors contre 58 % dedans, l'air froid extérieur contient
    # ici moins d'eau en valeur absolue : l'IA reçoit les deux informations.
    assert outdoor_ah < indoor_ah
    assert "relative_humidity_alone_is_not_enough" in air["interpretation_rule"]


def test_h2_daikin_temperature_never_becomes_weather_or_compressor_difficulty_fact() -> None:
    start, end, samples = _two_hours()
    h2 = ThermalAnalysisService(FakeSource(samples)).analyse(start, end)["expertise_h2"]

    terrace = h2["last_hour"]["terrace_microclimate"]
    assert terrace["temperature_daikin_c"]["mean"] == 17.0
    assert terrace["daikin_minus_outdoor_reference_c"]["mean"] == 7.0
    assert "never_weather_reference" in terrace["interpretation_rule"]
    assert "never_proof_that_the_compressor_is_struggling" in terrace["interpretation_rule"]


def test_h2_enrichment_is_not_added_to_a_full_day() -> None:
    start, _, samples = _two_hours()
    end = start + timedelta(days=1)
    result = ThermalAnalysisService(FakeSource(samples)).analyse(start, end)
    assert "expertise_h2" not in result


def test_h2_historical_temperature_classifier_preserves_v5_semantics() -> None:
    stable = classify_temperature_evolution(0.05, 0.10)
    assert stable["id"] == "stable_both_hours"
    assert stable["threshold_c"] == 0.15

    stabilizing = classify_temperature_evolution(0.40, 0.10)
    assert stabilizing["id"] == "stabilizing_last_hour"

    reversal = classify_temperature_evolution(0.30, -0.30)
    assert reversal["id"] == "trend_reversal"

    warming_accelerating = classify_temperature_evolution(0.20, 0.50)
    assert warming_accelerating["id"] == "warming_accelerating"

    cooling_slowing = classify_temperature_evolution(-0.50, -0.20)
    assert cooling_slowing["id"] == "cooling_slowing"


def test_h2_classification_is_exposed_in_the_service_contract() -> None:
    start, end, samples = _two_hours()
    h2 = ThermalAnalysisService(FakeSource(samples)).analyse(start, end)["expertise_h2"]
    classification = h2["comparison"]["temperature_evolution_classification"]

    assert classification["id"] == "warming_accelerating"
    assert classification["threshold_c"] == 0.15
    assert classification["interpretation_rule"] == "deterministic_classification_not_causal_explanation"
