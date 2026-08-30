from __future__ import annotations

from math import exp, log
from statistics import mean

from .engine import compare_results
from .facts import build_thermal_facts


def _dt_minutes(a, b):
    return max(0.0, min((b.ts - a.ts).total_seconds() / 60.0, 15.0))


def _summary(values):
    values = [v for v in values if v is not None]
    if not values:
        return {"mean": None, "min": None, "max": None}
    return {
        "mean": round(mean(values), 2),
        "min": round(min(values), 2),
        "max": round(max(values), 2),
    }


def _weighted_summary(samples, value_fn):
    values = []
    weighted_total = 0.0
    weighted_minutes = 0.0
    known_samples = 0

    for sample in samples:
        value = value_fn(sample)
        if value is not None:
            values.append(value)
            known_samples += 1

    for a, b in zip(samples, samples[1:]):
        value = value_fn(a)
        dt = _dt_minutes(a, b)
        if value is not None and dt > 0:
            weighted_total += value * dt
            weighted_minutes += dt

    if not values:
        return {"mean": None, "min": None, "max": None, "coverage": 0.0}

    avg = weighted_total / weighted_minutes if weighted_minutes > 0 else mean(values)
    return {
        "mean": round(avg, 2),
        "min": round(min(values), 2),
        "max": round(max(values), 2),
        "coverage": round(known_samples / max(1, len(samples)), 3),
    }


def _dew_point_c(temp_c, relative_humidity_pct):
    if temp_c is None or relative_humidity_pct is None:
        return None
    if relative_humidity_pct <= 0 or relative_humidity_pct > 100:
        return None
    alpha = log(relative_humidity_pct / 100.0) + (17.62 * temp_c) / (243.12 + temp_c)
    return 243.12 * alpha / (17.62 - alpha)


def _absolute_humidity_g_m3(temp_c, relative_humidity_pct):
    if temp_c is None or relative_humidity_pct is None:
        return None
    if relative_humidity_pct < 0 or relative_humidity_pct > 100:
        return None
    saturation_hpa = 6.112 * exp((17.67 * temp_c) / (temp_c + 243.5))
    vapor_hpa = saturation_hpa * relative_humidity_pct / 100.0
    return 216.7 * vapor_hpa / (273.15 + temp_c)


def _temperature_trend(samples):
    usable = [(s.ts, s.temp_indoor) for s in samples if s.temp_indoor is not None]
    if len(usable) < 2:
        return {
            "first_c": usable[0][1] if usable else None,
            "last_c": usable[-1][1] if usable else None,
            "delta_c": None,
            "rate_c_per_hour": None,
        }
    first_ts, first_value = usable[0]
    last_ts, last_value = usable[-1]
    duration_hours = (last_ts - first_ts).total_seconds() / 3600.0
    delta = last_value - first_value
    return {
        "first_c": round(first_value, 2),
        "last_c": round(last_value, 2),
        "delta_c": round(delta, 2),
        "rate_c_per_hour": round(delta / duration_hours, 2) if duration_hours > 0 else None,
    }


def _setpoint_tracking(samples, band_c):
    levels = {}
    transitions = []
    previous_known = None

    for sample in samples:
        if sample.setpoint is None:
            continue
        if previous_known is not None and abs(sample.setpoint - previous_known) >= 0.05:
            transitions.append(
                {
                    "at": sample.ts.isoformat(),
                    "from_c": round(previous_known, 2),
                    "to_c": round(sample.setpoint, 2),
                }
            )
        previous_known = sample.setpoint

    within = 0.0
    above = 0.0
    below = 0.0
    deltas = []
    weighted_delta_total = 0.0
    weighted_delta_minutes = 0.0

    for a, b in zip(samples, samples[1:]):
        dt = _dt_minutes(a, b)
        if a.setpoint is not None and dt > 0:
            key = round(a.setpoint, 2)
            levels[key] = levels.get(key, 0.0) + dt
        if a.setpoint is None or a.temp_indoor is None or dt <= 0:
            continue
        delta = a.temp_indoor - a.setpoint
        deltas.append(delta)
        weighted_delta_total += delta * dt
        weighted_delta_minutes += dt
        if delta > band_c:
            above += dt
        elif delta < -band_c:
            below += dt
        else:
            within += dt

    if samples:
        last = samples[-1]
        if last.setpoint is not None and last.temp_indoor is not None:
            deltas.append(last.temp_indoor - last.setpoint)

    latest = None
    for sample in reversed(samples):
        if sample.setpoint is not None:
            latest = sample.setpoint
            break

    delta_summary = _summary(deltas)
    if weighted_delta_minutes > 0:
        delta_summary["mean"] = round(weighted_delta_total / weighted_delta_minutes, 2)

    return {
        "latest_setpoint_c": round(latest, 2) if latest is not None else None,
        "active_levels": [
            {"setpoint_c": value, "minutes": round(minutes, 1)}
            for value, minutes in sorted(levels.items())
        ],
        "transition_count": len(transitions),
        "transitions": transitions,
        "indoor_minus_setpoint_c": delta_summary,
        "tracking_band_c": band_c,
        "within_tracking_band_minutes": round(within, 1),
        "above_tracking_band_minutes": round(above, 1),
        "below_tracking_band_minutes": round(below, 1),
        "interpretation_rule": (
            "evaluate_against_active_setpoint_and_report_transitions; "
            "do_not_use_a_24h_average_setpoint_as_the_target"
        ),
    }


def _air_properties(samples):
    indoor_ah = _weighted_summary(
        samples,
        lambda s: _absolute_humidity_g_m3(s.temp_indoor, s.humidity_indoor),
    )
    outdoor_ah = _weighted_summary(
        samples,
        lambda s: _absolute_humidity_g_m3(s.temp_outdoor_ref, s.humidity_outdoor),
    )
    indoor_dp = _weighted_summary(
        samples,
        lambda s: _dew_point_c(s.temp_indoor, s.humidity_indoor),
    )
    outdoor_dp = _weighted_summary(
        samples,
        lambda s: _dew_point_c(s.temp_outdoor_ref, s.humidity_outdoor),
    )
    ah_delta = _weighted_summary(
        samples,
        lambda s: (
            _absolute_humidity_g_m3(s.temp_outdoor_ref, s.humidity_outdoor)
            - _absolute_humidity_g_m3(s.temp_indoor, s.humidity_indoor)
            if _absolute_humidity_g_m3(s.temp_outdoor_ref, s.humidity_outdoor) is not None
            and _absolute_humidity_g_m3(s.temp_indoor, s.humidity_indoor) is not None
            else None
        ),
    )
    return {
        "indoor_absolute_humidity_g_m3": indoor_ah,
        "outdoor_absolute_humidity_g_m3": outdoor_ah,
        "outdoor_minus_indoor_absolute_humidity_g_m3": ah_delta,
        "indoor_dew_point_c": indoor_dp,
        "outdoor_dew_point_c": outdoor_dp,
        "interpretation_rule": (
            "use_temperature_and_moisture_content_together; "
            "relative_humidity_alone_is_not_enough_to_judge_ventilation"
        ),
    }


def _latest_observation(samples, attr):
    for sample in reversed(samples):
        value = getattr(sample, attr)
        if value is not None:
            return {"value": round(value, 3), "at": sample.ts.isoformat()}
    return {"value": None, "at": None}


def _hourly_energy_observation(samples):
    cool = _latest_observation(samples, "cool_energy_last_hour")
    heat = _latest_observation(samples, "heat_energy_last_hour")
    return {
        "cool_energy_last_hour_kwh": cool,
        "heat_energy_last_hour_kwh": heat,
        "interpretation_rule": (
            "these_are_last-hour_sensor_observations; "
            "do_not_sum_repeated_5-minute_samples"
        ),
    }


def _terrace_microclimate(samples):
    temp = _weighted_summary(samples, lambda s: s.temp_outdoor_daikin)
    delta = _weighted_summary(
        samples,
        lambda s: (
            s.temp_outdoor_daikin - s.temp_outdoor_ref
            if s.temp_outdoor_daikin is not None and s.temp_outdoor_ref is not None
            else None
        ),
    )
    hotter_minutes = 0.0
    comparable_minutes = 0.0
    for a, b in zip(samples, samples[1:]):
        if a.temp_outdoor_daikin is None or a.temp_outdoor_ref is None:
            continue
        dt = _dt_minutes(a, b)
        comparable_minutes += dt
        if a.temp_outdoor_daikin > a.temp_outdoor_ref:
            hotter_minutes += dt
    return {
        "temperature_daikin_c": temp,
        "daikin_minus_outdoor_reference_c": delta,
        "daikin_hotter_than_reference_minutes": round(hotter_minutes, 1),
        "comparable_minutes": round(comparable_minutes, 1),
        "interpretation_rule": (
            "terrace_microclimate_context_only; never_weather_reference; "
            "never_proof_that_the_compressor_is_struggling_or_inefficient"
        ),
    }


def build_h2_segment(samples, analysis, cfg):
    return {
        "analysis": analysis,
        "thermal_facts": build_thermal_facts(analysis),
        "temperature_trend": _temperature_trend(samples),
        "setpoint_tracking": _setpoint_tracking(samples, cfg.setpoint_tracking_band_c),
        "air_properties": _air_properties(samples),
        "hourly_energy_observation": _hourly_energy_observation(samples),
        "terrace_microclimate": _terrace_microclimate(samples),
    }


def _value(obj, *path):
    current = obj
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _delta(current, previous, *path):
    a = _value(current, *path)
    b = _value(previous, *path)
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return round(a - b, 3)
    return None


def compare_h2_segments(last_hour, previous_hour):
    return {
        "engine_delta": compare_results(last_hour["analysis"], previous_hour["analysis"]),
        "indoor_temperature_mean_delta_c": _delta(
            last_hour, previous_hour, "analysis", "temperature_indoor", "mean"
        ),
        "indoor_temperature_trend_delta_c": _delta(
            last_hour, previous_hour, "temperature_trend", "delta_c"
        ),
        "indoor_humidity_mean_delta_pct": _delta(
            last_hour, previous_hour, "analysis", "humidity_indoor", "mean"
        ),
        "active_setpoint_delta_c": _delta(
            last_hour, previous_hour, "setpoint_tracking", "latest_setpoint_c"
        ),
        "indoor_minus_setpoint_mean_delta_c": _delta(
            last_hour,
            previous_hour,
            "setpoint_tracking",
            "indoor_minus_setpoint_c",
            "mean",
        ),
        "indoor_absolute_humidity_mean_delta_g_m3": _delta(
            last_hour,
            previous_hour,
            "air_properties",
            "indoor_absolute_humidity_g_m3",
            "mean",
        ),
        "outdoor_absolute_humidity_mean_delta_g_m3": _delta(
            last_hour,
            previous_hour,
            "air_properties",
            "outdoor_absolute_humidity_g_m3",
            "mean",
        ),
        "cool_energy_last_hour_observation_delta_kwh": _delta(
            last_hour,
            previous_hour,
            "hourly_energy_observation",
            "cool_energy_last_hour_kwh",
            "value",
        ),
        "heat_energy_last_hour_observation_delta_kwh": _delta(
            last_hour,
            previous_hour,
            "hourly_energy_observation",
            "heat_energy_last_hour_kwh",
            "value",
        ),
        "terrace_microclimate_mean_delta_c": _delta(
            last_hour,
            previous_hour,
            "terrace_microclimate",
            "daikin_minus_outdoor_reference_c",
            "mean",
        ),
        "interpretation_rule": (
            "last_hour_is_primary; previous_hour_is_reference; "
            "deltas_are_facts_not_causal_explanations"
        ),
    }


def build_h2_expertise(
    previous_samples,
    last_samples,
    previous_analysis,
    last_analysis,
    cfg,
    previous_period,
    last_period,
):
    previous_hour = build_h2_segment(previous_samples, previous_analysis, cfg)
    last_hour = build_h2_segment(last_samples, last_analysis, cfg)
    return {
        "profile": "h2_last_hour_vs_previous_hour",
        "primary_period": last_period,
        "reference_period": previous_period,
        "last_hour": last_hour,
        "previous_hour": previous_hour,
        "comparison": compare_h2_segments(last_hour, previous_hour),
        "analysis_contract": {
            "primary_rule": "analyse_the_last_hour_and_compare_it_with_the_previous_hour",
            "setpoint_rule": "judge_temperature_against_the_active_setpoint_and_expose_transitions",
            "ventilation_rule": (
                "temperature_difference_alone_never_implies_that_ventilation_is_the_best_thermal_strategy; "
                "consider_temperature_moisture_content_openings_and_daikin_context"
            ),
            "terrace_rule": (
                "daikin_outdoor_temperature_is_terrace_microclimate_context_only_and_never_proves_compressor_difficulty"
            ),
            "causality_rule": "facts_and_correlations_must_not_be_presented_as_proven_causes",
            "decision_rule": "the_app_does_not_command_equipment; the_llm_explains_and_advises",
        },
    }
