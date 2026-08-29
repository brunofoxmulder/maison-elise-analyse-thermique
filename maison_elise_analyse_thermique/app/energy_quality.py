from __future__ import annotations


def apply_energy_temporal_coverage(
    analysis: dict,
    samples,
    start,
    end,
    max_gap_minutes: float = 15.0,
    minimum_coverage_for_period_fact: float = 0.90,
) -> dict:
    """Remplace la couverture par paires par une couverture temporelle.

    Le compteur journalier reste la source de l'énergie. Cette fonction ne
    recalcule pas les kWh : elle mesure seulement la part de la période pour
    laquelle deux lectures consécutives permettent une transition exploitable.
    Une baisse du compteur le même jour (par exemple le reset constaté juste
    après minuit) n'est pas considérée comme un intervalle couvert.
    """
    energy = analysis.setdefault("compressor_energy", {})
    pair_coverage = energy.get("coverage")

    period_minutes = max(0.0, (end - start).total_seconds() / 60.0)
    covered_minutes = 0.0
    rows = sorted(samples, key=lambda sample: sample.ts)

    for a, b in zip(rows, rows[1:]):
        v1 = a.compressor_energy_day
        v2 = b.compressor_energy_day
        if v1 is None or v2 is None:
            continue

        dt = (b.ts - a.ts).total_seconds() / 60.0
        if dt <= 0:
            continue

        transition_usable = v2 >= v1 or b.ts.date() != a.ts.date()
        if not transition_usable:
            continue

        covered_minutes += min(dt, max_gap_minutes)

    temporal_coverage = (
        covered_minutes / period_minutes if period_minutes > 0 else 0.0
    )
    temporal_coverage = round(min(1.0, temporal_coverage), 3)

    energy["pair_coverage"] = pair_coverage
    energy["coverage"] = temporal_coverage
    energy["covered_minutes"] = round(covered_minutes, 1)
    energy["period_minutes"] = round(period_minutes, 1)
    energy["coverage_rule"] = "usable_counter_intervals_over_requested_period"
    energy["period_fact_allowed"] = temporal_coverage >= minimum_coverage_for_period_fact
    energy["minimum_coverage_for_period_fact"] = minimum_coverage_for_period_fact
    return analysis
