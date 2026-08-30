from __future__ import annotations


def apply_period_temporal_coverage(analysis: dict, samples, start, end, max_gap_minutes: float = 15.0, minimum_coverage_for_strong_period_summary: float = 0.90) -> dict:
    period_minutes = max(0.0, (end - start).total_seconds() / 60.0)
    covered_minutes = 0.0
    rows = sorted(samples, key=lambda sample: sample.ts)
    for a, b in zip(rows, rows[1:]):
        dt = (b.ts - a.ts).total_seconds() / 60.0
        if dt > 0: covered_minutes += min(dt, max_gap_minutes)
    coverage = covered_minutes / period_minutes if period_minutes > 0 else 0.0
    coverage = round(min(1.0, coverage), 3)
    analysis["period_coverage"] = {"coverage":coverage,"covered_minutes":round(covered_minutes,1),"period_minutes":round(period_minutes,1),"strong_period_summary_allowed":coverage >= minimum_coverage_for_strong_period_summary,"minimum_coverage_for_strong_period_summary":minimum_coverage_for_strong_period_summary,"coverage_rule":"observed_intervals_over_requested_period"}
    return analysis
