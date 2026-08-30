from __future__ import annotations

DEFAULT_NEAR_DUPLICATE_TOLERANCE_SECONDS = 1.0

def deduplicate_near_samples(samples, tolerance_seconds=DEFAULT_NEAR_DUPLICATE_TOLERANCE_SECONDS):
    ordered = sorted(samples, key=lambda sample: sample.ts)
    if not ordered:
        return [], {"near_duplicate_tolerance_seconds": tolerance_seconds, "near_duplicate_groups": [], "near_duplicate_dropped_count": 0}
    groups=[]; current=[ordered[0]]
    for sample in ordered[1:]:
        if 0 <= (sample.ts-current[0].ts).total_seconds() <= tolerance_seconds: current.append(sample)
        else: groups.append(current); current=[sample]
    groups.append(current)
    deduplicated=[]; duplicate_groups=[]; dropped=0
    for group in groups:
        kept=group[-1]; deduplicated.append(kept)
        if len(group)>1:
            dropped += len(group)-1
            duplicate_groups.append({"first_ts":group[0].ts.isoformat(),"kept_ts":kept.ts.isoformat(),"sample_count":len(group),"dropped_count":len(group)-1,"policy":"keep_latest_snapshot_within_anchor_window"})
    return deduplicated, {"near_duplicate_tolerance_seconds":tolerance_seconds,"near_duplicate_groups":duplicate_groups,"near_duplicate_dropped_count":dropped}
