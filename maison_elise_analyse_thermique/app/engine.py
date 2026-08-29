from collections import Counter
from statistics import mean
from .quality import filter_outdoor_temperature_anomalies


def _values(samples, attr):
    return [getattr(s, attr) for s in samples if getattr(s, attr) is not None]


def _summary(values):
    if not values:
        return {"mean": None, "min": None, "max": None}
    return {
        "mean": round(mean(values), 2),
        "min": round(min(values), 2),
        "max": round(max(values), 2),
    }


def _coverage(samples, attr):
    if not samples:
        return 0.0
    return round(sum(getattr(s, attr) is not None for s in samples) / len(samples), 3)


def _dt_minutes(a, b):
    return max(0.0, min((b.ts - a.ts).total_seconds() / 60.0, 15.0))


def _time_weighted_summary(samples, attr):
    values = _values(samples, attr)
    if not values:
        return {"mean": None, "min": None, "max": None}

    weighted_total = 0.0
    weighted_minutes = 0.0
    for a, b in zip(samples, samples[1:]):
        value = getattr(a, attr)
        dt = _dt_minutes(a, b)
        if value is not None and dt > 0:
            weighted_total += value * dt
            weighted_minutes += dt

    avg = weighted_total / weighted_minutes if weighted_minutes > 0 else mean(values)
    return {
        "mean": round(avg, 2),
        "min": round(min(values), 2),
        "max": round(max(values), 2),
    }


def _time_weighted_delta_summary(samples):
    values = []
    weighted_total = 0.0
    weighted_minutes = 0.0

    for a, b in zip(samples, samples[1:]):
        if a.temp_outdoor_ref is None or a.temp_indoor is None:
            continue
        delta = a.temp_outdoor_ref - a.temp_indoor
        values.append(delta)
        dt = _dt_minutes(a, b)
        if dt > 0:
            weighted_total += delta * dt
            weighted_minutes += dt

    if samples:
        last = samples[-1]
        if last.temp_outdoor_ref is not None and last.temp_indoor is not None:
            values.append(last.temp_outdoor_ref - last.temp_indoor)

    if not values:
        return {"mean": None, "min": None, "max": None}
    avg = weighted_total / weighted_minutes if weighted_minutes > 0 else mean(values)
    return {
        "mean": round(avg, 2),
        "min": round(min(values), 2),
        "max": round(max(values), 2),
    }


def _minutes_by_state(samples, attr):
    totals = Counter()
    for a, b in zip(samples, samples[1:]):
        state = getattr(a, attr) or "unknown"
        totals[state] += _dt_minutes(a, b)
    return {k: round(v, 1) for k, v in totals.items()}


def _open_minutes(samples, attr):
    total = 0.0
    for a, b in zip(samples, samples[1:]):
        if getattr(a, attr) is True:
            total += _dt_minutes(a, b)
    return round(total, 1)


def _energy_from_daily_counter(samples):
    vals = [(s.ts, s.compressor_energy_day) for s in samples if s.compressor_energy_day is not None]
    if len(vals) < 2:
        return {"kwh": None, "coverage": 0.0}

    total, used = 0.0, 0
    for (t1, v1), (t2, v2) in zip(vals, vals[1:]):
        if v2 >= v1:
            total += v2 - v1
            used += 1
        elif t2.date() != t1.date():
            total += max(v2, 0.0)
            used += 1

    return {"kwh": round(total, 3), "coverage": round(used / max(1, len(vals) - 1), 3)}


def _sun_geometry(sample, cfg):
    """Présence du soleil dans la fenêtre géométrique connue du salon.

    Cette métrique ne dépend ni du lux ni du modèle d'exposition directe.
    """
    if sample.sun_azimuth is None or sample.sun_elevation is None:
        return None
    return (
        cfg.sun_azimuth_in <= sample.sun_azimuth <= cfg.sun_azimuth_out
        and sample.sun_elevation > cfg.sun_elevation_min
    )


def _bright_sky(sample, cfg):
    """Contexte de forte luminosité solaire, indépendant de l'azimut.

    Ce signal ne mesure pas l'énergie solaire et ne prouve aucun gain thermique.
    Il sert à conserver le cas d'un ciel très lumineux par diffusion/réflexion,
    y compris lorsque le soleil est hors de la fenêtre géométrique.
    """
    if sample.lux is None or sample.sun_elevation is None:
        return None
    if sample.sun_elevation <= cfg.sun_elevation_min:
        return False
    return sample.lux >= cfg.bright_sky_lux_min


def _sun_lux_threshold(elevation, cfg):
    if elevation is None or elevation <= cfg.sun_elevation_min:
        return None
    if elevation >= cfg.sun_elevation_effective_model_max:
        return None
    if elevation < 15:
        return cfg.sun_lux_stage_15
    if elevation < 35:
        return cfg.sun_lux_stage_35
    if elevation < 45:
        return cfg.sun_lux_stage_45
    if elevation < 55:
        return cfg.sun_lux_stage_55
    return cfg.sun_lux_stage_65


def _sun_effective(sample, cfg):
    geometry = _sun_geometry(sample, cfg)
    if geometry is None or sample.lux is None:
        return None
    if not geometry:
        return False
    threshold = _sun_lux_threshold(sample.sun_elevation, cfg)
    if threshold is None:
        return False
    return sample.lux >= threshold


def _sun_minutes(samples, cfg):
    geometric = 0.0
    geometric_known = 0.0
    bright = 0.0
    bright_known = 0.0
    bright_outside_geometry = 0.0
    effective = 0.0
    effective_known = 0.0
    shutter_sum = 0.0
    shutter_weight = 0.0

    for a, b in zip(samples, samples[1:]):
        dt = _dt_minutes(a, b)

        geometry = _sun_geometry(a, cfg)
        if geometry is not None:
            geometric_known += dt
            if geometry:
                geometric += dt

        bright_flag = _bright_sky(a, cfg)
        if bright_flag is not None:
            bright_known += dt
            if bright_flag:
                bright += dt
                if geometry is False:
                    bright_outside_geometry += dt

        effective_flag = _sun_effective(a, cfg)
        if effective_flag is None:
            continue
        effective_known += dt
        if effective_flag:
            effective += dt
            if a.shutter_salon is not None:
                shutter_sum += a.shutter_salon * dt
                shutter_weight += dt

    total_known_window = sum(_dt_minutes(a, b) for a, b in zip(samples, samples[1:]))

    return {
        "geometric_window_minutes": round(geometric, 1),
        "geometric_known_minutes": round(geometric_known, 1),
        "geometric_coverage": round(geometric_known / max(1.0, total_known_window), 3) if len(samples) > 1 else 0.0,
        "bright_sky_minutes": round(bright, 1),
        "bright_sky_outside_geometry_minutes": round(bright_outside_geometry, 1),
        "bright_sky_known_minutes": round(bright_known, 1),
        "bright_sky_lux_threshold": cfg.bright_sky_lux_min,
        "bright_sky_rule": "daylight_and_lux_threshold_context_only",
        "effective_minutes": round(effective, 1),
        "known_minutes": round(effective_known, 1),
        "coverage": round(effective_known / max(1.0, total_known_window), 3) if len(samples) > 1 else 0.0,
        "effective_model_rule": "geometry_and_lux_stages_below_effective_model_max",
        "effective_model_max_elevation": cfg.sun_elevation_effective_model_max,
        "salon_shutter_mean_during_effective_sun": (
            round(shutter_sum / shutter_weight, 1) if shutter_weight else None
        ),
    }


def _weighted_mean(total, weight):
    return round(total / weight, 2) if weight > 0 else None


def _cross_contexts(samples, cfg):
    """Croise des faits simultanés sans transformer une corrélation en cause."""
    totals = Counter()
    cooling_freq_sum = 0.0
    cooling_freq_weight = 0.0
    cooling_humidity_sum = 0.0
    cooling_humidity_weight = 0.0
    non_cooling_humidity_sum = 0.0
    non_cooling_humidity_weight = 0.0

    for a, b in zip(samples, samples[1:]):
        dt = _dt_minutes(a, b)
        cooling = a.hvac_action == "cooling"
        any_opening = a.window_open is True or a.door_window_open is True
        sun = _sun_effective(a, cfg) is True

        if cooling:
            if any_opening:
                totals["cooling_while_any_opening_minutes"] += dt
            if a.window_open is True:
                totals["cooling_while_window_open_minutes"] += dt
            if a.door_window_open is True:
                totals["cooling_while_door_window_open_minutes"] += dt
            if sun:
                totals["cooling_during_effective_sun_minutes"] += dt
            if a.temp_outdoor_ref is not None and a.temp_indoor is not None:
                if a.temp_outdoor_ref < a.temp_indoor:
                    totals["cooling_while_outdoor_cooler_than_indoor_minutes"] += dt
                elif a.temp_outdoor_ref > a.temp_indoor:
                    totals["cooling_while_outdoor_warmer_than_indoor_minutes"] += dt
            if a.setpoint is not None and a.temp_indoor is not None and a.temp_indoor <= a.setpoint:
                totals["cooling_at_or_below_setpoint_minutes"] += dt
            if a.compressor_frequency is not None and dt > 0:
                cooling_freq_sum += a.compressor_frequency * dt
                cooling_freq_weight += dt
            if a.humidity_indoor is not None and dt > 0:
                cooling_humidity_sum += a.humidity_indoor * dt
                cooling_humidity_weight += dt
        elif a.humidity_indoor is not None and dt > 0:
            non_cooling_humidity_sum += a.humidity_indoor * dt
            non_cooling_humidity_weight += dt

        if sun and a.shutter_salon is not None:
            if a.shutter_salon >= cfg.shutter_open_min:
                totals["effective_sun_with_salon_shutter_open_minutes"] += dt
            if a.shutter_salon <= cfg.shutter_closed_max:
                totals["effective_sun_with_salon_shutter_closed_minutes"] += dt

    return {
        "cooling_while_any_opening_minutes": round(totals["cooling_while_any_opening_minutes"], 1),
        "cooling_while_window_open_minutes": round(totals["cooling_while_window_open_minutes"], 1),
        "cooling_while_door_window_open_minutes": round(totals["cooling_while_door_window_open_minutes"], 1),
        "cooling_during_effective_sun_minutes": round(totals["cooling_during_effective_sun_minutes"], 1),
        "cooling_while_outdoor_cooler_than_indoor_minutes": round(totals["cooling_while_outdoor_cooler_than_indoor_minutes"], 1),
        "cooling_while_outdoor_warmer_than_indoor_minutes": round(totals["cooling_while_outdoor_warmer_than_indoor_minutes"], 1),
        "cooling_at_or_below_setpoint_minutes": round(totals["cooling_at_or_below_setpoint_minutes"], 1),
        "effective_sun_with_salon_shutter_open_minutes": round(totals["effective_sun_with_salon_shutter_open_minutes"], 1),
        "effective_sun_with_salon_shutter_closed_minutes": round(totals["effective_sun_with_salon_shutter_closed_minutes"], 1),
        "compressor_frequency_mean_during_cooling": _weighted_mean(cooling_freq_sum, cooling_freq_weight),
        "humidity_indoor_mean_during_cooling": _weighted_mean(cooling_humidity_sum, cooling_humidity_weight),
        "humidity_indoor_mean_outside_cooling": _weighted_mean(non_cooling_humidity_sum, non_cooling_humidity_weight),
        "interpretation_rule": "context_only_not_causality",
    }


def _quality_summary(cleaned, anomalies, cfg):
    outdoor_coverage = _coverage(cleaned, "temp_outdoor_ref")
    suspect = [a for a in anomalies if not a.get("rejected", False)]
    rejected = [a for a in anomalies if a.get("rejected", False)]

    reasons = []
    if suspect:
        reasons.append("outdoor_temperature_suspect_steps")
    if rejected:
        reasons.append("outdoor_temperature_rejected_jumps")
    if outdoor_coverage < cfg.minimum_coverage_for_strong_claim:
        reasons.append("outdoor_temperature_insufficient_coverage")

    return {
        "strong_claim_allowed": not reasons,
        "strong_claim_block_reasons": reasons,
        "outdoor_temperature_anomalies": anomalies,
        "outdoor_temperature_suspect_count": len(suspect),
        "outdoor_temperature_rejected_count": len(rejected),
        "outdoor_temperature_coverage": outdoor_coverage,
    }


def analyse_samples(samples, cfg):
    samples = sorted(samples, key=lambda s: s.ts)
    cleaned, anomalies = filter_outdoor_temperature_anomalies(samples, cfg)

    freq = _values(cleaned, "compressor_frequency")
    vs = _values(cleaned, "shutter_salon")
    vt = _values(cleaned, "shutter_terrasse")
    lux = _values(cleaned, "lux")
    delta_summary = _time_weighted_delta_summary(cleaned)
    delta_coverage = round(sum(
        s.temp_outdoor_ref is not None and s.temp_indoor is not None for s in cleaned
    ) / max(1, len(cleaned)), 3)

    return {
        "samples": len(cleaned),
        "temperature_indoor": {**_time_weighted_summary(cleaned, "temp_indoor"), "coverage": _coverage(cleaned, "temp_indoor")},
        "temperature_outdoor_reference": {**_time_weighted_summary(cleaned, "temp_outdoor_ref"), "coverage": _coverage(cleaned, "temp_outdoor_ref")},
        "delta_outdoor_minus_indoor": {**delta_summary, "coverage": delta_coverage},
        "humidity_indoor": {**_time_weighted_summary(cleaned, "humidity_indoor"), "coverage": _coverage(cleaned, "humidity_indoor")},
        "humidity_outdoor": {**_time_weighted_summary(cleaned, "humidity_outdoor"), "coverage": _coverage(cleaned, "humidity_outdoor")},
        "hvac_action_minutes": _minutes_by_state(cleaned, "hvac_action"),
        "hvac_mode_minutes": _minutes_by_state(cleaned, "hvac_mode"),
        "compressor_frequency": {**_summary(freq), "coverage": _coverage(cleaned, "compressor_frequency")},
        "compressor_energy": _energy_from_daily_counter(cleaned),
        "openings": {
            "window_open_minutes": _open_minutes(cleaned, "window_open"),
            "door_window_open_minutes": _open_minutes(cleaned, "door_window_open"),
        },
        "shutters": {
            "salon": {**_summary(vs), "coverage": _coverage(cleaned, "shutter_salon")},
            "terrasse": {**_summary(vt), "coverage": _coverage(cleaned, "shutter_terrasse")},
        },
        "lux": {**_summary(lux), "coverage": _coverage(cleaned, "lux")},
        "solar_exposure": _sun_minutes(cleaned, cfg),
        "cross_contexts": _cross_contexts(cleaned, cfg),
        "quality": _quality_summary(cleaned, anomalies, cfg),
    }


def compare_results(current, reference):
    def delta(path):
        a, b = current, reference
        for key in path:
            a = a.get(key) if isinstance(a, dict) else None
            b = b.get(key) if isinstance(b, dict) else None
        if isinstance(a, (int, float)) and isinstance(b, (int, float)):
            return round(a - b, 3)
        return None

    return {
        "temperature_indoor_mean_delta_c": delta(["temperature_indoor", "mean"]),
        "temperature_outdoor_mean_delta_c": delta(["temperature_outdoor_reference", "mean"]),
        "compressor_energy_delta_kwh": delta(["compressor_energy", "kwh"]),
        "window_open_minutes_delta": delta(["openings", "window_open_minutes"]),
        "door_window_open_minutes_delta": delta(["openings", "door_window_open_minutes"]),
        "geometric_sun_minutes_delta": delta(["solar_exposure", "geometric_window_minutes"]),
        "bright_sky_minutes_delta": delta(["solar_exposure", "bright_sky_minutes"]),
        "bright_sky_outside_geometry_minutes_delta": delta(["solar_exposure", "bright_sky_outside_geometry_minutes"]),
        "effective_sun_minutes_delta": delta(["solar_exposure", "effective_minutes"]),
        "cooling_while_any_opening_minutes_delta": delta(["cross_contexts", "cooling_while_any_opening_minutes"]),
        "cooling_during_effective_sun_minutes_delta": delta(["cross_contexts", "cooling_during_effective_sun_minutes"]),
    }
