from __future__ import annotations

from collections import Counter


COMPRESSOR_REGIME_THRESHOLDS = {
    "very_low_max_hz": 15.0,
    "low_max_hz": 22.0,
    "medium_max_hz": 35.0,
}

MAX_INTERVAL_MINUTES = 15.0


def classify_compressor_frequency(hz: float | None) -> str | None:
    """Classe la fréquence du compresseur Daikin Stylish pour l'expertise.

    Cette famille est un repère de lecture pratique pour les rapports, pas un
    barème constructeur ni une conversion de puissance.
    """
    if hz is None:
        return None
    hz = float(hz)
    if hz < 0:
        return None
    if hz == 0:
        return "arrêté"
    if hz <= COMPRESSOR_REGIME_THRESHOLDS["very_low_max_hz"]:
        return "très faible"
    if hz <= COMPRESSOR_REGIME_THRESHOLDS["low_max_hz"]:
        return "faible"
    if hz <= COMPRESSOR_REGIME_THRESHOLDS["medium_max_hz"]:
        return "moyen"
    return "fort"


def compressor_regime_context(mean_hz: float | None, max_hz: float | None = None) -> dict:
    return {
        "mean_regime_family": classify_compressor_frequency(mean_hz),
        "max_regime_family": classify_compressor_frequency(max_hz),
        "thresholds_hz": {
            "arrêté": "0",
            "très faible": ">0-15",
            "faible": "16-22",
            "moyen": "23-35",
            "fort": ">35",
        },
        "rule": "practical_reading_only_not_manufacturer_rating_not_power_conversion",
    }


def compressor_regime_durations(samples) -> dict:
    """Calcule les durées par famille de fréquence sans inventer les manques.

    L'intervalle est porté par le relevé de début et plafonné à 15 minutes,
    comme le reste du moteur thermique. Une fréquence absente reste inconnue.
    """
    totals = Counter()
    unknown_minutes = 0.0

    for a, b in zip(samples, samples[1:]):
        dt = max(
            0.0,
            min((b.ts - a.ts).total_seconds() / 60.0, MAX_INTERVAL_MINUTES),
        )
        if dt <= 0:
            continue
        regime = classify_compressor_frequency(a.compressor_frequency)
        if regime is None:
            unknown_minutes += dt
        else:
            totals[regime] += dt

    known_minutes = sum(totals.values())
    total_minutes = known_minutes + unknown_minutes
    ordered_regimes = ("arrêté", "très faible", "faible", "moyen", "fort")
    dominant_regime = None
    if known_minutes > 0:
        dominant_regime = max(
            ordered_regimes,
            key=lambda name: (totals[name], -ordered_regimes.index(name)),
        )

    return {
        "minutes": {name: round(totals[name], 1) for name in ordered_regimes},
        "known_minutes": round(known_minutes, 1),
        "unknown_minutes": round(unknown_minutes, 1),
        "coverage": round(known_minutes / total_minutes, 3) if total_minutes > 0 else 0.0,
        "dominant_regime": dominant_regime,
        "thresholds_hz": {
            "arrêté": "0",
            "très faible": ">0-15",
            "faible": "16-22",
            "moyen": "23-35",
            "fort": ">35",
        },
        "rule": (
            "deterministic_duration_from_recorded_frequency; missing_frequency_is_unknown; "
            "regimes_are_practical_context_not_power_or_energy_conversion"
        ),
    }
