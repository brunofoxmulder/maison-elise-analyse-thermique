from __future__ import annotations


def _get(obj, *path):
    current = obj
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _cover_state(value):
    if not isinstance(value, (int, float)):
        return "unknown"
    if value <= 5:
        return "closed"
    if value >= 95:
        return "open"
    return "partially_open"


def build_assist_brief_facts(result: dict) -> dict | None:
    """Compile only the deterministic facts allowed in the short Assist answer.

    The purpose is ergonomic and defensive: the short answer must describe the
    last hour, with the previous hour only as a reference. It must not drift to
    the two-hour top-level aggregate or invent causal explanations.
    """
    expertise = result.get("expertise_h2")
    if not isinstance(expertise, dict):
        return None

    last = expertise.get("last_hour") or {}
    analysis = last.get("analysis") or {}
    comparison = expertise.get("comparison") or {}
    setpoint = last.get("setpoint_tracking") or {}
    trend = last.get("temperature_trend") or {}
    air = last.get("air_properties") or {}
    energy = last.get("hourly_energy_observation") or {}
    forecast = expertise.get("forecast_h4") or {}

    salon_position = _get(analysis, "shutters", "salon", "mean")
    terrasse_position = _get(analysis, "shutters", "terrasse", "mean")

    points = forecast.get("points") if forecast.get("available") else []
    if not isinstance(points, list):
        points = []

    return {
        "scope": {
            "primary_period": expertise.get("primary_period"),
            "reference_period": expertise.get("reference_period"),
            "rule": (
                "short_answer_must_use_last_hour_only_for_current_metrics; "
                "previous_hour_is_reference_only; never_use_two_hour_top_level_durations"
            ),
        },
        "temperature": {
            "indoor_mean_c": _get(analysis, "temperature_indoor", "mean"),
            "indoor_delta_c_last_hour": trend.get("delta_c"),
            "active_setpoint_c": setpoint.get("latest_setpoint_c"),
            "indoor_minus_setpoint_mean_c": _get(
                setpoint, "indoor_minus_setpoint_c", "mean"
            ),
            "comparison_previous_hour": {
                "classification_id": _get(
                    comparison,
                    "temperature_evolution_classification",
                    "id",
                ),
                "classification_label_fr": _get(
                    comparison,
                    "temperature_evolution_classification",
                    "label_fr",
                ),
                "indoor_mean_delta_c": comparison.get(
                    "indoor_temperature_mean_delta_c"
                ),
            },
        },
        "outdoor": {
            "reference_mean_c": _get(
                analysis, "temperature_outdoor_reference", "mean"
            ),
            "outdoor_minus_indoor_mean_c": _get(
                analysis, "delta_outdoor_minus_indoor", "mean"
            ),
            "rule": (
                "outdoor_temperature_is_context_not_a_proven_cause_of_hvac_operation; "
                "never_say_it_explains_continuous_cooling_by_itself"
            ),
        },
        "humidity": {
            "indoor_relative_humidity_mean_pct": _get(
                analysis, "humidity_indoor", "mean"
            ),
            "outdoor_relative_humidity_mean_pct": _get(
                analysis, "humidity_outdoor", "mean"
            ),
            "indoor_absolute_humidity_mean_g_m3": _get(
                air, "indoor_absolute_humidity_g_m3", "mean"
            ),
            "outdoor_absolute_humidity_mean_g_m3": _get(
                air, "outdoor_absolute_humidity_g_m3", "mean"
            ),
            "rule": (
                "relative_humidity_alone_must_not_drive_ventilation_or_dehumidification_advice"
            ),
        },
        "daikin": {
            "cooling_minutes_last_hour": _get(
                analysis, "hvac_action_minutes", "cooling"
            ),
            "heating_minutes_last_hour": _get(
                analysis, "hvac_action_minutes", "heating"
            ),
            "compressor_frequency_mean_hz": _get(
                analysis, "compressor_frequency", "mean"
            ),
            "cool_energy_last_hour_kwh": _get(
                energy, "cool_energy_last_hour_kwh", "value"
            ),
            "heat_energy_last_hour_kwh": _get(
                energy, "heat_energy_last_hour_kwh", "value"
            ),
            "rule": (
                "describe_observed_operation_only; do_not_claim_cause_or_inefficiency_without_supporting_facts"
            ),
        },
        "openings": {
            "window_open_minutes_last_hour": _get(
                analysis, "openings", "window_open_minutes"
            ),
            "door_window_open_minutes_last_hour": _get(
                analysis, "openings", "door_window_open_minutes"
            ),
        },
        "shutters": {
            "salon": {
                "mean_open_pct": salon_position,
                "state": _cover_state(salon_position),
            },
            "terrasse": {
                "mean_open_pct": terrasse_position,
                "state": _cover_state(terrasse_position),
            },
            "rule": (
                "0_percent_is_closed_100_percent_is_open; "
                "never_describe_open_shutters_as_closed; "
                "only_recommend_a_position_change_when_the_solar_facts_support_a_current_benefit"
            ),
        },
        "solar": {
            "effective_sun_minutes_last_hour": _get(
                analysis, "solar_exposure", "effective_minutes"
            ),
            "bright_sky_minutes_last_hour": _get(
                analysis, "solar_exposure", "bright_sky_minutes"
            ),
            "effective_sun_with_salon_shutter_open_minutes": _get(
                analysis,
                "cross_contexts",
                "effective_sun_with_salon_shutter_open_minutes",
            ),
            "rule": (
                "do_not_recommend_closing_shutters_solely_because_it_is_daytime; "
                "use_effective_solar_context_and_current_shutter_state"
            ),
        },
        "forecast": {
            "available": bool(forecast.get("available")),
            "points": points,
            "rule": (
                "only_describe_values_present_in_these_points; "
                "never_extend_beyond_the_last_point_or_invent_tomorrow"
            ),
        },
        "short_answer_rules": [
            "few_plain_sentences_in_order_constat_analyse_preconisation_a_venir",
            "constat_and_analysis_must_be_grounded_in_this_object_only",
            "preconisation_is_optional_when_no_useful_action_is_supported",
            "prefer_no_action_needed_over_forced_advice",
            "never_mix_two_hour_aggregate_metrics_into_the_short_answer",
            "never_turn_a_correlation_into_a_proven_cause",
        ],
    }
