from __future__ import annotations


COMPRESSOR_REGIME_THRESHOLDS = {
    "very_low_max_hz": 15.0,
    "low_max_hz": 22.0,
    "medium_max_hz": 35.0,
}


def classify_compressor_frequency(hz: float | None) -> str | None:
    """Classe grossièrement la fréquence du compresseur Daikin Stylish.

    Cette famille est un repère de lecture pratique pour les rapports, pas un
    barème constructeur ni une conversion de puissance.
    """
    if hz is None:
        return None
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
            "très faible": "<=15",
            "faible": "16-22",
            "moyen": "23-35",
            "fort": ">35",
        },
        "rule": "practical_reading_only_not_manufacturer_rating_not_power_conversion",
    }
