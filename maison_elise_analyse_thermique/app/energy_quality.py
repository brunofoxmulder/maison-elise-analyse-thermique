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


def apply_midnight_cumulative_counter_total(
    analysis: dict,
    samples,
    start,
    end,
    max_end_lag_minutes: float = 15.0,
) -> dict:
    """Use the daily cumulative Daikin counter when the requested period starts at midnight.

    ``Energie_compresseur_jour`` is already cumulative since local midnight.
    For a midnight-anchored period, the latest fresh counter value therefore
    represents the energy used since the beginning of the requested period.
    This remains valid even if the Sheet starts exposing that counter late in
    the day. A non-midnight period keeps the incremental/difference method.
    """
    energy = analysis.setdefault("compressor_energy", {})

    start_is_midnight = (
        start.hour == 0
        and start.minute == 0
        and start.second == 0
        and start.microsecond == 0
    )
    duration_minutes = max(0.0, (end - start).total_seconds() / 60.0)
    if not start_is_midnight or duration_minutes > 25 * 60:
        return analysis

    values = [
        (sample.ts, float(sample.compressor_energy_day))
        for sample in sorted(samples, key=lambda sample: sample.ts)
        if sample.compressor_energy_day is not None
    ]
    if not values:
        return analysis

    last_ts, last_value = values[-1]
    end_lag_minutes = max(0.0, (end - last_ts).total_seconds() / 60.0)
    end_alignment_good = end_lag_minutes <= max_end_lag_minutes

    energy["incremental_kwh"] = energy.get("kwh")
    energy["daily_counter_last_value_kwh"] = round(last_value, 3)
    energy["daily_counter_last_timestamp"] = last_ts.isoformat()
    energy["daily_counter_end_lag_minutes"] = round(end_lag_minutes, 1)
    energy["daily_counter_end_alignment_good"] = end_alignment_good
    energy["daily_counter_rule"] = (
        "period_starts_at_local_midnight_so_latest_daily_cumulative_counter_is_period_total"
    )

    if end_alignment_good:
        energy["kwh"] = round(last_value, 3)
        energy["period_fact_allowed"] = True
        energy["source_rule"] = "daily_cumulative_counter_last_value_from_midnight"
    return analysis
