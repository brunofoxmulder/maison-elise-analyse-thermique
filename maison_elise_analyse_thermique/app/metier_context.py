from __future__ import annotations


METIER_CONTEXT_VERSION = "V1.1"
METIER_CONTEXT_SOURCE = "referentiel_metier_clim.txt V1.1 / Scripts - Maison Cognitive"

METIER_CONTEXT = {
    "version": METIER_CONTEXT_VERSION,
    "source": METIER_CONTEXT_SOURCE,
    "role": {
        "app": "collect_filter_calculate_compare_compile_deterministic_facts",
        "llm": "interpret_contextualize_form_hypotheses_and_give_expert_opinion",
        "principle": "expertise_not_absolute_truth_and_not_a_recitation_of_numbers",
    },
    "numeric_truth": "deterministic_App_values_then_recorded_HA_measurements",
    "setpoint": {
        "source": "recorded_Consigne",
        "wording": "écart à la consigne / écart moyen à la consigne",
        "tracking_band_c": 0.5,
        "tracking_band_semantics": "descriptive_only_not_manufacturer_performance_threshold",
    },
    "life_state": {
        "source": "historical_sheet_column_Prise_de_comptage",
        "on": "awake",
        "off": "asleep",
        "unknown": "do_not_infer",
        "rule": "never_replace_historical_period_state_with_current_Home_Assistant_state",
    },
    "daikin": {
        "model_context": "Daikin Stylish Inverter",
        "hvac_action_rule": "cooling_or_heating_action_does_not_prove_continuous_compressor_operation",
        "compressor_frequency_unit": "Hz",
        "compressor_regimes": {
            "arrêté": "0 Hz",
            "très faible": ">0 à 15 Hz",
            "faible": "16 à 22 Hz",
            "moyen": "23 à 35 Hz",
            "fort": ">35 Hz",
        },
        "regime_semantics": "practical_context_not_manufacturer_rating_not_Hz_to_W_or_kWh_conversion",
        "power_w_rule": "instantaneous_W_values_are_not_used_for_current_thermal_expertise",
    },
    "reporting": {
        "day_compressor_solicitation": (
            "for_a_day_report_show_the_deterministic_compressor_regime_durations_when_available; "
            "list_stopped_very_low_low_medium_and_high_minutes_and_unknown_minutes_if_nonzero; "
            "also_keep_mean_frequency_and_dominant_regime; do_not_replace_this_detail_with_only_one_average"
        ),
        "source_rule": "use_analysis.compressor_regimes_and_thermal_facts_compressor_regime_durations_without_recalculation",
    },
    "outdoor_temperature": {
        "reference": "general_outdoor_context_used_by_App",
        "daikin": "terrace_outdoor_unit_microclimate_only",
        "rule": "Daikin_outdoor_temperature_alone_does_not_prove_compressor_effort_efficiency_or_consumption",
    },
    "openings": {
        "rule": "opening_is_not_automatically_favourable_or_adverse",
        "airflow": "no_measured_airflow_so_wind_or_temperature_difference_only_indicates_potential",
        "cooling_with_opening": "never_automatically_label_as_waste",
    },
    "humidity": {
        "rule": "relative_humidity_alone_is_insufficient_when_indoor_and_outdoor_temperatures_differ",
        "preferred_context": "temperature_plus_absolute_humidity_or_dew_point_when_available",
    },
    "shutters": {
        "position_0": "closed",
        "position_100": "open",
        "rule": "position_or_simultaneity_alone_does_not_prove_thermal_causality",
    },
    "tempo": {
        "rule": "use_only_when_period_context_is_explicitly_provided",
        "red_peak_context": "intentional_climate_shutdown_can_be_an_energy_strategy_not_an_anomaly",
    },
    "home": {
        "surface_m2": 25,
        "height_m": 2.5,
        "volume_m3": 62.5,
        "thermal_inertia": "high",
        "salon_window": "East_double_glazing",
        "terrace_door_window": "NorthEast_double_glazing",
    },
    "reasoning": {
        "causality": "correlation_or_sequence_does_not_prove_causality",
        "uncertainty": "incomplete_or_imperfect_data_can_change_the_interpretation",
        "language": "probabilistic_language_is_appropriate_when_claim_exceeds_direct_measurement",
        "freedom": "LLM_may_link_observations_propose_explanations_hypotheses_advice_or_no_action",
    },
}
