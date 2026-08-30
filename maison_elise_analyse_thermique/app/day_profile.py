from __future__ import annotations

from collections import Counter

from .day_interactions import build_opening_interactions


TRACKING_BAND_C = 0.5
MAX_INTERVAL_MINUTES = 15.0
DAY_CONTEXT_MINUTES = 130.0


def _dt_minutes(a, b) -> float:
    return max(0.0, min((b.ts - a.ts).total_seconds() / 60.0, MAX_INTERVAL_MINUTES))


def _active_mode(value: str | None) -> str | None:
    mode = (value or "").strip().lower()
    if mode in {"cool", "cooling"}:
        return "cool"
    if mode in {"heat", "heating"}:
        return "heat"
    return None


def _append_segment(segments: list[dict], start, end) -> None:
    if segments and segments[-1]["end"] == start.isoformat():
        segments[-1]["end"] = end.isoformat()
        return
    segments.append({"start": start.isoformat(), "end": end.isoformat()})


def _observed_span_minutes(samples) -> float:
    ordered = sorted(samples, key=lambda sample: sample.ts)
    if len(ordered) < 2:
        return 0.0
    return max(0.0, (ordered[-1].ts - ordered[0].ts).total_seconds() / 60.0)


def build_setpoint_profiles(samples) -> dict:
    """Describe the recorded requested temperatures without inventing a schedule.

    The source of truth is the recorded ``Consigne`` value carried by each
    ThermalSample. Values are grouped separately for cooling and heating so the
    same machinery works in both seasons. The two longest requested
    temperatures are highlighted for each active HVAC mode, while every
    observed regime remains available for audit.
    """

    ordered = sorted(samples, key=lambda sample: sample.ts)
    accumulators: dict[tuple[str, float], dict] = {}
    mode_minutes = Counter()

    for a, b in zip(ordered, ordered[1:]):
        dt = _dt_minutes(a, b)
        mode = _active_mode(a.hvac_mode)
        if dt <= 0 or mode is None or a.setpoint is None:
            continue

        setpoint = round(float(a.setpoint), 2)
        key = (mode, setpoint)
        bucket = accumulators.setdefault(
            key,
            {
                "minutes": 0.0,
                "indoor_sum": 0.0,
                "indoor_weight": 0.0,
                "signed_delta_sum": 0.0,
                "abs_error_sum": 0.0,
                "tracking_weight": 0.0,
                "within_band_minutes": 0.0,
                "hvac_action_minutes": Counter(),
                "segments": [],
            },
        )
        bucket["minutes"] += dt
        mode_minutes[mode] += dt
        _append_segment(bucket["segments"], a.ts, b.ts)

        action = (a.hvac_action or "unknown").strip().lower() or "unknown"
        bucket["hvac_action_minutes"][action] += dt

        if a.temp_indoor is not None:
            indoor = float(a.temp_indoor)
            delta = indoor - setpoint
            bucket["indoor_sum"] += indoor * dt
            bucket["indoor_weight"] += dt
            bucket["signed_delta_sum"] += delta * dt
            bucket["abs_error_sum"] += abs(delta) * dt
            bucket["tracking_weight"] += dt
            if abs(delta) <= TRACKING_BAND_C:
                bucket["within_band_minutes"] += dt

    modes: dict[str, dict] = {}
    for mode in ("cool", "heat"):
        total = float(mode_minutes[mode])
        regimes = []
        for (regime_mode, setpoint), bucket in accumulators.items():
            if regime_mode != mode:
                continue
            indoor_weight = bucket["indoor_weight"]
            tracking_weight = bucket["tracking_weight"]
            regimes.append(
                {
                    "setpoint_c": setpoint,
                    "minutes": round(bucket["minutes"], 1),
                    "share_of_mode": round(bucket["minutes"] / total, 3) if total > 0 else 0.0,
                    "indoor_mean_c": (
                        round(bucket["indoor_sum"] / indoor_weight, 2)
                        if indoor_weight > 0
                        else None
                    ),
                    "mean_delta_indoor_minus_setpoint_c": (
                        round(bucket["signed_delta_sum"] / tracking_weight, 2)
                        if tracking_weight > 0
                        else None
                    ),
                    "mean_abs_tracking_error_c": (
                        round(bucket["abs_error_sum"] / tracking_weight, 2)
                        if tracking_weight > 0
                        else None
                    ),
                    "within_0_5c_minutes": round(bucket["within_band_minutes"], 1),
                    "within_0_5c_share": (
                        round(bucket["within_band_minutes"] / tracking_weight, 3)
                        if tracking_weight > 0
                        else None
                    ),
                    "hvac_action_minutes": {
                        key: round(value, 1)
                        for key, value in sorted(bucket["hvac_action_minutes"].items())
                    },
                    "segments": bucket["segments"],
                }
            )

        regimes.sort(key=lambda item: (-item["minutes"], item["setpoint_c"]))
        if regimes:
            modes[mode] = {
                "total_minutes": round(total, 1),
                "distinct_requested_temperatures_c": [item["setpoint_c"] for item in regimes],
                "dominant_two_requested_temperatures_c": [
                    item["setpoint_c"] for item in regimes[:2]
                ],
                "regimes": regimes,
            }

    dominant_mode = None
    if modes:
        dominant_mode = max(modes, key=lambda mode: modes[mode]["total_minutes"])

    result = {
        "dominant_active_hvac_mode": dominant_mode,
        "modes": modes,
        "tracking_band_c": TRACKING_BAND_C,
        "tracking_band_semantics": "descriptive_tracking_only_not_a_comfort_threshold",
        "setpoint_source_rule": "recorded_Consigne_is_truth_never_hardcode_requested_temperatures",
        "two_temperature_rule": (
            "for_each_active_cooling_or_heating_mode_highlight_the_two_longest_recorded_requested_"
            "temperatures_when_two_are_present;_keep_all_other_observed_regimes_for_audit"
        ),
    }

    # Keep the validated H-2 contract unchanged. Rich opening/context material is
    # attached only for periods longer than the H-2 profile.
    if _observed_span_minutes(ordered) > DAY_CONTEXT_MINUTES:
        result["opening_interactions"] = build_opening_interactions(ordered)
        result["day_expertise_guardrails"] = {
            "evidence_rule": (
                "distinguish_fact_observation_hypothesis_and_uncertainty; "
                "coexistence_or_sequence_does_not_prove_causality"
            ),
            "openings_rule": (
                "describe_when_and_in_what_measured_context_openings_were_used; "
                "do_not_claim_that_they_helped_or_harmed_without_validated_historical_evidence"
            ),
            "counterfactual_rule": (
                "do_not_say_the_user_should_have_opened_or_closed; this_profile_does_not_yet_have_"
                "validated_house_specific_experience_for_counterfactual_advice"
            ),
            "energy_qualification_rule": (
                "do_not_call_energy_low_moderate_high_optimal_or_excessive_without_an_explicit_"
                "validated_comparison_or_baseline"
            ),
            "shutter_rule": (
                "shutter_position_and_solar_context_are_measured_facts; do_not_say_shutters_allowed_"
                "or_caused_temperature_regulation_without_supporting_evidence"
            ),
            "outdoor_temperature_rule": (
                "outdoor_temperature_alone_never_explains_continuous_cooling_or_heating"
            ),
            "historical_day_rule": (
                "for_a_past_day_prefer_a_retrospective_performance_balance; do_not_invent_actions_"
                "for_today_or_future_conditions_that_are_not_in_the_requested_analysis"
            ),
        }

    return result
