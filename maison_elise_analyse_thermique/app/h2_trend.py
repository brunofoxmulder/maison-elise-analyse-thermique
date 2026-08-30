from __future__ import annotations


DEFAULT_TREND_THRESHOLD_C = 0.15


def classify_temperature_evolution(
    previous_delta_c: float | None,
    last_delta_c: float | None,
    threshold_c: float = DEFAULT_TREND_THRESHOLD_C,
) -> dict:
    """Qualifie l'évolution H−2 avec la règle historique Horaire V5.

    Cette logique est volontairement déterministe et reproduit le
    ``qualifier_tendance(h1, h2)`` du Pyscript V5.0.5 A+ validé terrain.
    La dernière heure reste le sujet principal ; l'heure précédente sert de
    référence pour qualifier stabilité, inversion, accélération ou ralentissement.
    """

    base = {
        "previous_hour_delta_c": previous_delta_c,
        "last_hour_delta_c": last_delta_c,
        "threshold_c": threshold_c,
        "source_rule": "pyscript_horaire_v5_qualifier_tendance",
        "interpretation_rule": "deterministic_classification_not_causal_explanation",
    }

    if previous_delta_c is None or last_delta_c is None:
        return {
            **base,
            "id": "indeterminate",
            "label_fr": "indéterminée",
        }

    if abs(last_delta_c) < threshold_c:
        if abs(previous_delta_c) < threshold_c:
            return {
                **base,
                "id": "stable_both_hours",
                "label_fr": "stabilité sur les deux heures",
            }
        return {
            **base,
            "id": "stabilizing_last_hour",
            "label_fr": "stabilisation pendant la seconde heure",
        }

    if previous_delta_c * last_delta_c < 0:
        return {
            **base,
            "id": "trend_reversal",
            "label_fr": "inversion de tendance",
        }

    if last_delta_c > 0:
        if abs(last_delta_c) > abs(previous_delta_c) + threshold_c:
            return {
                **base,
                "id": "warming_accelerating",
                "label_fr": "réchauffement en accélération",
            }
        if abs(last_delta_c) + threshold_c < abs(previous_delta_c):
            return {
                **base,
                "id": "warming_slowing",
                "label_fr": "réchauffement en ralentissement",
            }
        return {
            **base,
            "id": "warming_regular",
            "label_fr": "réchauffement régulier",
        }

    if abs(last_delta_c) > abs(previous_delta_c) + threshold_c:
        return {
            **base,
            "id": "cooling_accelerating",
            "label_fr": "refroidissement en accélération",
        }
    if abs(last_delta_c) + threshold_c < abs(previous_delta_c):
        return {
            **base,
            "id": "cooling_slowing",
            "label_fr": "refroidissement en ralentissement",
        }
    return {
        **base,
        "id": "cooling_regular",
        "label_fr": "refroidissement régulier",
    }
