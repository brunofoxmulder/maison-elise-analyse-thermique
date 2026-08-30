from __future__ import annotations


_TREND_LABELS = {
    "indeterminate": "évolution indéterminée",
    "stable_both_hours": "stable sur les deux heures",
    "stabilizing_last_hour": "stabilisation sur la dernière heure",
    "trend_reversal": "inversion de tendance",
    "warming_accelerating": "réchauffement qui accélère",
    "warming_slowing": "réchauffement qui ralentit",
    "warming_regular": "réchauffement régulier",
    "cooling_accelerating": "refroidissement qui accélère",
    "cooling_slowing": "refroidissement qui ralentit",
    "cooling_regular": "refroidissement régulier",
}


def _get(obj, *path):
    current = obj
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _num(value, digits=1):
    if not isinstance(value, (int, float)):
        return "n/d"
    return f"{value:.{digits}f}".replace(".", ",")


def _position(value):
    if not isinstance(value, (int, float)):
        return "n/d"
    rounded = round(value)
    if value <= 5:
        state = "fermé"
    elif value >= 95:
        state = "ouvert"
    else:
        state = "partiellement ouvert"
    return f"{rounded} % ({state})"


def notification_title(result: dict) -> str:
    if isinstance(result.get("expertise_h2"), dict):
        return "Analyse thermique — heure"
    return "Analyse thermique"


def build_notification_report(result: dict) -> str:
    """Compile un rapport factuel détaillé sans interprétation causale LLM."""
    expertise = result.get("expertise_h2")
    if isinstance(expertise, dict):
        last = expertise.get("last_hour") or {}
        analysis = last.get("analysis") or {}
        trend = last.get("temperature_trend") or {}
        setpoint = last.get("setpoint_tracking") or {}
        air = last.get("air_properties") or {}
        energy = last.get("hourly_energy_observation") or {}
        comparison = expertise.get("comparison") or {}
        forecast = expertise.get("forecast_h4") or {}
        quality = expertise.get("data_window") or {}
        period = expertise.get("primary_period") or {}

        indoor = analysis.get("temperature_indoor") or {}
        outdoor = analysis.get("temperature_outdoor_reference") or {}
        humidity = analysis.get("humidity_indoor") or {}
        hvac = analysis.get("hvac_action_minutes") or {}
        freq = analysis.get("compressor_frequency") or {}
        openings = analysis.get("openings") or {}
        shutters = analysis.get("shutters") or {}

        lines = [
            f"Période principale : {period.get('start', 'n/d')} → {period.get('end', 'n/d')}",
            (
                f"Salon : {_num(indoor.get('mean'))} °C en moyenne "
                f"({_num(indoor.get('min'))} à {_num(indoor.get('max'))} °C), "
                f"consigne active {_num(setpoint.get('latest_setpoint_c'))} °C, "
                f"évolution {_num(trend.get('delta_c'))} °C."
            ),
            (
                f"Comparaison heure précédente : "
                f"{_TREND_LABELS.get(_get(comparison, 'temperature_evolution_classification', 'classification'), _get(comparison, 'temperature_evolution_classification', 'classification') or 'n/d')}; "
                f"écart de moyenne {_num(comparison.get('indoor_temperature_mean_delta_c'), 2)} °C."
            ),
            (
                f"Extérieur fiable : {_num(outdoor.get('mean'))} °C. "
                f"Humidité intérieure : {_num(humidity.get('mean'), 0)} %. "
                f"Humidité absolue int./ext. : "
                f"{_num(_get(air, 'indoor_absolute_humidity_g_m3', 'mean'))} / "
                f"{_num(_get(air, 'outdoor_absolute_humidity_g_m3', 'mean'))} g/m³."
            ),
            (
                f"Daikin : refroidissement {_num(hvac.get('cooling'), 0)} min, "
                f"fréquence compresseur moyenne {_num(freq.get('mean'))} Hz, "
                f"énergie dernière heure {_num(_get(energy, 'cool_energy_last_hour_kwh', 'value'), 2)} kWh."
            ),
            (
                f"Ouvrants : fenêtre {_num(openings.get('window_open_minutes'), 0)} min, "
                f"porte-fenêtre {_num(openings.get('door_window_open_minutes'), 0)} min. "
                f"Volets : salon {_position(_get(shutters, 'salon', 'mean'))}, "
                f"terrasse {_position(_get(shutters, 'terrasse', 'mean'))}. "
                f"Convention : 0 % = fermé, 100 % = ouvert."
            ),
            (
                f"Qualité : {quality.get('last_hour_samples', 'n/d')} relevés sur la dernière heure; "
                f"retard du dernier relevé {_num(quality.get('requested_end_to_observed_end_lag_minutes'))} min."
            ),
        ]

        points = forecast.get("points") if forecast.get("available") else []
        if isinstance(points, list) and points:
            rendered = []
            for point in points:
                if not isinstance(point, dict):
                    continue
                rendered.append(
                    f"{point.get('datetime', 'n/d')} : {_num(point.get('temperature'))} °C"
                    + (f", {point.get('condition')}" if point.get("condition") else "")
                )
            if rendered:
                lines.append("À venir H+4 : " + " ; ".join(rendered) + ".")
        else:
            lines.append("À venir H+4 : prévision indisponible ; aucune valeur future n’est inventée.")

        return "\n".join(lines)

    period = result.get("period") or {}
    facts_container = result.get("thermal_facts") or {}
    facts = facts_container.get("facts") if isinstance(facts_container, dict) else []
    lines = [f"Période : {period.get('start', 'n/d')} → {period.get('end', 'n/d')}"]
    if isinstance(facts, list):
        for fact in facts[:12]:
            if not isinstance(fact, dict):
                continue
            label = fact.get("label", fact.get("id", "Fait"))
            value = fact.get("value")
            unit = fact.get("unit")
            lines.append(f"{label} : {value}" + (f" {unit}" if unit else ""))
    return "\n".join(lines)
