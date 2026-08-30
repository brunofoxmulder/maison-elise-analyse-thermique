from __future__ import annotations

from .compressor_regime import compressor_regime_context


def _fact(fact_id, priority, label, value, unit=None, context=None):
    item = {
        "id": fact_id,
        "priority": priority,
        "label": label,
        "value": value,
        "interpretation": "fact_only_not_causality",
    }
    if unit is not None:
        item["unit"] = unit
    if context is not None:
        item["context"] = context
    return item


def build_thermal_facts(analysis: dict, max_facts: int = 15) -> dict:
    """Construit un résumé compact de faits déjà calculés."""
    facts = []
    quality = analysis.get("quality", {})
    period_coverage = analysis.get("period_coverage", {})
    cross = analysis.get("cross_contexts", {})
    openings = analysis.get("openings", {})
    solar = analysis.get("solar_exposure", {})
    energy = analysis.get("compressor_energy", {})
    hvac = analysis.get("hvac_action_minutes", {})

    sample_count = analysis.get("samples", 0) or 0
    no_data = sample_count == 0
    if no_data:
        facts.append(_fact("quality_no_samples", 110, "Aucune donnée thermique disponible sur la période demandée", 0, context={"sample_count": 0}))

    period_summary_strong_claim_allowed = period_coverage.get("strong_period_summary_allowed", True) and not no_data
    if not period_summary_strong_claim_allowed and not no_data:
        facts.append(_fact("quality_period_coverage_partial", 100, "Couverture temporelle insuffisante pour résumer fortement toute la période", period_coverage.get("coverage"), context={"covered_minutes": period_coverage.get("covered_minutes"), "period_minutes": period_coverage.get("period_minutes"), "minimum_coverage": period_coverage.get("minimum_coverage_for_strong_period_summary")}))

    outdoor_context_strong_claim_allowed = quality.get("outdoor_context_strong_claim_allowed", quality.get("strong_claim_allowed", True)) and not no_data
    outdoor_context_block_reasons = quality.get("outdoor_context_strong_claim_block_reasons", quality.get("strong_claim_block_reasons", []))
    if not outdoor_context_strong_claim_allowed and not no_data:
        facts.append(_fact("quality_outdoor_context_strong_claim_blocked", 100, "Conclusion forte dépendant de la température extérieure interdite par la qualité des données", False, context=outdoor_context_block_reasons))

    cooling_open = cross.get("cooling_while_any_opening_minutes", 0) or 0
    if cooling_open > 0:
        facts.append(_fact("cooling_while_opening", 100, "Refroidissement avec au moins un ouvrant ouvert", cooling_open, "min"))

    window_open = openings.get("window_open_minutes", 0) or 0
    door_open = openings.get("door_window_open_minutes", 0) or 0
    if window_open > 0 or door_open > 0:
        facts.append(_fact("openings", 95, "Durée d'ouverture mesurée", {"window": window_open, "door_window": door_open}, "min"))

    kwh = energy.get("kwh")
    energy_context = {"coverage": energy.get("coverage"), "covered_minutes": energy.get("covered_minutes"), "period_minutes": energy.get("period_minutes")}
    if kwh is not None and energy.get("period_fact_allowed", True):
        facts.append(_fact("compressor_energy", 90, "Énergie compresseur mesurée sur la période", kwh, "kWh", context=energy_context))
    elif kwh is not None:
        facts.append(_fact("compressor_energy_partial", 65, "Énergie compresseur mesurée seulement sur la partie couverte de la période", kwh, "kWh", context=energy_context))

    cooling_minutes = hvac.get("cooling")
    if cooling_minutes is not None:
        facts.append(_fact("cooling_duration", 90, "Durée de refroidissement", cooling_minutes, "min"))

    cooler = cross.get("cooling_while_outdoor_cooler_than_indoor_minutes", 0) or 0
    if cooler > 0:
        facts.append(_fact("cooling_outdoor_cooler", 85, "Refroidissement alors que l'extérieur mesuré était plus frais que l'intérieur", cooler, "min"))

    at_setpoint = cross.get("cooling_at_or_below_setpoint_minutes", 0) or 0
    if at_setpoint > 0:
        facts.append(_fact("cooling_at_or_below_setpoint", 85, "Refroidissement alors que la température intérieure était à ou sous la consigne", at_setpoint, "min"))

    cooling_sun = cross.get("cooling_during_effective_sun_minutes", 0) or 0
    if cooling_sun > 0:
        facts.append(_fact("cooling_during_effective_sun", 80, "Refroidissement pendant une exposition solaire effective", cooling_sun, "min"))

    indoor = analysis.get("temperature_indoor", {})
    if indoor.get("mean") is not None:
        facts.append(_fact("indoor_temperature", 80, "Température intérieure", {"mean": indoor.get("mean"), "min": indoor.get("min"), "max": indoor.get("max")}, "°C", context={"coverage": indoor.get("coverage")}))

    outdoor = analysis.get("temperature_outdoor_reference", {})
    if outdoor.get("mean") is not None:
        facts.append(_fact("outdoor_temperature_reference", 75, "Température extérieure de référence", {"mean": outdoor.get("mean"), "min": outdoor.get("min"), "max": outdoor.get("max")}, "°C", context={"coverage": outdoor.get("coverage")}))

    freq = cross.get("compressor_frequency_mean_during_cooling")
    if freq is not None:
        freq_summary = analysis.get("compressor_frequency", {})
        facts.append(_fact(
            "compressor_frequency_cooling",
            75,
            "Fréquence compresseur moyenne pendant le refroidissement",
            freq,
            "Hz",
            context=compressor_regime_context(freq, freq_summary.get("max")),
        ))

    effective_sun = solar.get("effective_minutes", 0) or 0
    if effective_sun > 0:
        facts.append(_fact("effective_sun", 70, "Exposition solaire effective", effective_sun, "min", context={"salon_shutter_mean_position": solar.get("salon_shutter_mean_during_effective_sun")}))

    bright_outside = solar.get("bright_sky_outside_geometry_minutes", 0) or 0
    if bright_outside > 0:
        facts.append(_fact("bright_sky_outside_sun_geometry", 70, "Ciel très lumineux alors que le soleil était hors de la fenêtre géométrique", bright_outside, "min", context={"lux_threshold": solar.get("bright_sky_lux_threshold"), "interpretation": "diffuse_or_reflected_solar_context_possible_not_proven_heat_gain"}))

    humidity = analysis.get("humidity_indoor", {})
    if humidity.get("mean") is not None:
        facts.append(_fact("indoor_humidity", 60, "Humidité intérieure", {"mean": humidity.get("mean"), "min": humidity.get("min"), "max": humidity.get("max")}, "%", context={"coverage": humidity.get("coverage")}))

    facts.sort(key=lambda item: (-item["priority"], item["id"]))
    facts = facts[:max_facts]
    return {"facts": facts, "fact_count": len(facts), "max_facts": max_facts, "no_data": no_data, "period_summary_strong_claim_allowed": period_summary_strong_claim_allowed, "period_coverage": period_coverage, "outdoor_context_strong_claim_allowed": outdoor_context_strong_claim_allowed, "outdoor_context_strong_claim_block_reasons": outdoor_context_block_reasons, "interpretation_rule": "llm_may_explain_but_not_recalculate_or_invent_causality"}
