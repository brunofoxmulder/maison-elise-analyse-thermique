from __future__ import annotations


_LABELS = {
    "temperature_indoor_mean_delta_c": ("Écart de température intérieure moyenne", "°C"),
    "temperature_outdoor_mean_delta_c": ("Écart de température extérieure moyenne", "°C"),
    "compressor_energy_delta_kwh": ("Écart d'énergie compresseur", "kWh"),
    "window_open_minutes_delta": ("Écart de durée d'ouverture fenêtre", "min"),
    "door_window_open_minutes_delta": ("Écart de durée d'ouverture porte-fenêtre", "min"),
    "geometric_sun_minutes_delta": ("Écart de présence solaire dans la fenêtre géométrique", "min"),
    "bright_sky_minutes_delta": ("Écart de durée de ciel très lumineux", "min"),
    "bright_sky_outside_geometry_minutes_delta": ("Écart de ciel très lumineux hors fenêtre solaire géométrique", "min"),
    "effective_sun_minutes_delta": ("Écart d'exposition solaire effective", "min"),
    "cooling_while_any_opening_minutes_delta": ("Écart de refroidissement avec ouvrant ouvert", "min"),
    "cooling_during_effective_sun_minutes_delta": ("Écart de refroidissement pendant soleil effectif", "min"),
}


def build_comparison_facts(delta: dict) -> dict:
    facts = []
    for key, (label, unit) in _LABELS.items():
        value = delta.get(key)
        if value is None:
            continue
        facts.append({
            "id": key,
            "label": label,
            "value": value,
            "unit": unit,
            "interpretation": "fact_only_not_causality",
        })

    return {
        "facts": facts,
        "fact_count": len(facts),
        "interpretation_rule": "deterministic_delta_only_no_recalculation",
    }
