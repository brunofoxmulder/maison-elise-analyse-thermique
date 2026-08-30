from __future__ import annotations

import math
from collections import Counter


MAX_INTERVAL_MINUTES = 15.0


def _dt_minutes(a, b) -> float:
    return max(0.0, min((b.ts - a.ts).total_seconds() / 60.0, MAX_INTERVAL_MINUTES))


def _absolute_humidity_g_m3(temp_c, rh_percent):
    if temp_c is None or rh_percent is None:
        return None
    temp = float(temp_c)
    rh = max(0.0, min(100.0, float(rh_percent)))
    saturation_hpa = 6.112 * math.exp((17.67 * temp) / (temp + 243.5))
    vapor_hpa = saturation_hpa * rh / 100.0
    return 216.7 * vapor_hpa / (273.15 + temp)


def _new_segment(start):
    return {
        "start": start.isoformat(),
        "end": start.isoformat(),
        "minutes": 0.0,
        "hvac_action_minutes": Counter(),
        "temp_delta_sum": 0.0,
        "temp_delta_weight": 0.0,
        "moisture_delta_sum": 0.0,
        "moisture_delta_weight": 0.0,
        "compressor_frequency_sum": 0.0,
        "compressor_frequency_weight": 0.0,
    }


def _finish_segment(segment):
    if segment is None:
        return None
    temp_weight = segment.pop("temp_delta_weight")
    temp_sum = segment.pop("temp_delta_sum")
    moisture_weight = segment.pop("moisture_delta_weight")
    moisture_sum = segment.pop("moisture_delta_sum")
    freq_weight = segment.pop("compressor_frequency_weight")
    freq_sum = segment.pop("compressor_frequency_sum")
    segment["minutes"] = round(segment["minutes"], 1)
    segment["hvac_action_minutes"] = {
        key: round(value, 1)
        for key, value in sorted(segment["hvac_action_minutes"].items())
    }
    segment["mean_outdoor_minus_indoor_c"] = (
        round(temp_sum / temp_weight, 2) if temp_weight > 0 else None
    )
    segment["mean_outdoor_minus_indoor_absolute_humidity_g_m3"] = (
        round(moisture_sum / moisture_weight, 2) if moisture_weight > 0 else None
    )
    segment["mean_compressor_frequency_hz"] = (
        round(freq_sum / freq_weight, 2) if freq_weight > 0 else None
    )
    return segment


def _opening_profile(samples, attr: str) -> dict:
    ordered = sorted(samples, key=lambda sample: sample.ts)
    totals = Counter()
    segments = []
    current = None
    temp_delta_sum = 0.0
    temp_delta_weight = 0.0
    moisture_delta_sum = 0.0
    moisture_delta_weight = 0.0

    for a, b in zip(ordered, ordered[1:]):
        dt = _dt_minutes(a, b)
        is_open = getattr(a, attr) is True
        if dt <= 0:
            continue

        if not is_open:
            if current is not None:
                segments.append(_finish_segment(current))
                current = None
            continue

        if current is None:
            current = _new_segment(a.ts)
        current["end"] = b.ts.isoformat()
        current["minutes"] += dt

        action = (a.hvac_action or "unknown").strip().lower() or "unknown"
        current["hvac_action_minutes"][action] += dt
        totals[f"hvac_{action}_minutes"] += dt
        totals["open_minutes"] += dt

        if a.temp_outdoor_ref is not None and a.temp_indoor is not None:
            delta = float(a.temp_outdoor_ref) - float(a.temp_indoor)
            current["temp_delta_sum"] += delta * dt
            current["temp_delta_weight"] += dt
            temp_delta_sum += delta * dt
            temp_delta_weight += dt
            if delta < 0:
                totals["outdoor_cooler_minutes"] += dt
            elif delta > 0:
                totals["outdoor_warmer_minutes"] += dt
            else:
                totals["outdoor_equal_minutes"] += dt

        indoor_ah = _absolute_humidity_g_m3(a.temp_indoor, a.humidity_indoor)
        outdoor_ah = _absolute_humidity_g_m3(a.temp_outdoor_ref, a.humidity_outdoor)
        if indoor_ah is not None and outdoor_ah is not None:
            moisture_delta = outdoor_ah - indoor_ah
            current["moisture_delta_sum"] += moisture_delta * dt
            current["moisture_delta_weight"] += dt
            moisture_delta_sum += moisture_delta * dt
            moisture_delta_weight += dt
            if moisture_delta < 0:
                totals["outdoor_drier_absolute_minutes"] += dt
            elif moisture_delta > 0:
                totals["outdoor_more_humid_absolute_minutes"] += dt

        if a.compressor_frequency is not None:
            frequency = float(a.compressor_frequency)
            current["compressor_frequency_sum"] += frequency * dt
            current["compressor_frequency_weight"] += dt

    if current is not None:
        segments.append(_finish_segment(current))

    return {
        "open_minutes": round(totals["open_minutes"], 1),
        "segments": segments,
        "cooling_while_open_minutes": round(totals["hvac_cooling_minutes"], 1),
        "heating_while_open_minutes": round(totals["hvac_heating_minutes"], 1),
        "idle_while_open_minutes": round(totals["hvac_idle_minutes"], 1),
        "off_while_open_minutes": round(totals["hvac_off_minutes"], 1),
        "outdoor_cooler_while_open_minutes": round(totals["outdoor_cooler_minutes"], 1),
        "outdoor_warmer_while_open_minutes": round(totals["outdoor_warmer_minutes"], 1),
        "outdoor_drier_absolute_while_open_minutes": round(
            totals["outdoor_drier_absolute_minutes"], 1
        ),
        "outdoor_more_humid_absolute_while_open_minutes": round(
            totals["outdoor_more_humid_absolute_minutes"], 1
        ),
        "mean_outdoor_minus_indoor_c_while_open": (
            round(temp_delta_sum / temp_delta_weight, 2)
            if temp_delta_weight > 0
            else None
        ),
        "mean_outdoor_minus_indoor_absolute_humidity_g_m3_while_open": (
            round(moisture_delta_sum / moisture_delta_weight, 2)
            if moisture_delta_weight > 0
            else None
        ),
    }


def build_opening_interactions(samples) -> dict:
    """Describe measured opening/HVAC/weather coexistence without inferring benefit.

    This deliberately does not claim that an opening helped or harmed thermal
    regulation. It only exposes the measured context so the LLM can describe
    what happened without inventing causality. Predictive learning is a separate
    future concern and is not part of this profile.
    """
    return {
        "window": _opening_profile(samples, "window_open"),
        "door_window": _opening_profile(samples, "door_window_open"),
        "influence_assessment": "not_established_by_this_profile",
        "counterfactual_recommendation": "not_allowed_without_validated_historical_evidence",
        "interpretation_rule": (
            "report_measured_opening_context_only; do_not_claim_that_opening_helped_or_harmed; "
            "do_not_say_the_user_should_have_opened_or_closed_without_validated_historical_evidence"
        ),
        "airflow_rule": "no_airflow_sensor_so_actual_air_exchange_is_unknown",
        "moisture_rule": (
            "absolute_humidity_is_derived_from_recorded_temperature_and_relative_humidity; "
            "relative_humidity_alone_must_not_drive_ventilation_claims"
        ),
    }
