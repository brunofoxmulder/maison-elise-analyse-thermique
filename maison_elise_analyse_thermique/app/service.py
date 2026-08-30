from datetime import timedelta

from .comparison_facts import build_comparison_facts
from .config import AnalysisConfig
from .energy_quality import apply_energy_temporal_coverage
from .engine import analyse_samples, compare_results
from .facts import build_thermal_facts
from .h2_expertise import build_h2_expertise
from .normalization import deduplicate_near_samples
from .periods import reference_period, validate_period
from .temporal_quality import apply_period_temporal_coverage


class ThermalAnalysisService:
    def __init__(self, source, config=None):
        self.source = source
        self.config = config or AnalysisConfig()

    def _prepare_period(self, start, end):
        raw_samples = self.source.load(start, end)
        samples, input_quality = deduplicate_near_samples(raw_samples)
        analysis = analyse_samples(samples, self.config)
        apply_period_temporal_coverage(analysis, samples, start, end)
        apply_energy_temporal_coverage(analysis, samples, start, end)
        analysis["input_quality"] = input_quality
        analysis["raw_samples"] = len(raw_samples)
        return analysis, samples

    def _analyse_period(self, start, end):
        analysis, _ = self._prepare_period(start, end)
        return analysis

    @staticmethod
    def _is_h2_period(start, end):
        duration_minutes = (end - start).total_seconds() / 60.0
        return 110.0 <= duration_minutes <= 130.0

    def _build_h2(self, end):
        last_start = end - timedelta(hours=1)
        previous_start = end - timedelta(hours=2)

        previous_analysis, previous_samples = self._prepare_period(
            previous_start,
            last_start,
        )
        last_analysis, last_samples = self._prepare_period(last_start, end)

        return build_h2_expertise(
            previous_samples=previous_samples,
            last_samples=last_samples,
            previous_analysis=previous_analysis,
            last_analysis=last_analysis,
            cfg=self.config,
            previous_period={
                "start": previous_start.isoformat(),
                "end": last_start.isoformat(),
            },
            last_period={
                "start": last_start.isoformat(),
                "end": end.isoformat(),
            },
        )

    def analyse(self, start, end, compare=None):
        validate_period(start, end)
        period = {"start": start.isoformat(), "end": end.isoformat()}
        current = self._analyse_period(start, end)
        current_facts = build_thermal_facts(current)
        out = {"period": period, "analysis": current, "thermal_facts": current_facts}

        # Le profil H-2 est enrichi automatiquement lorsque le client demande
        # environ deux heures. La dernière heure est le sujet principal ;
        # l'heure précédente est uniquement la référence immédiate.
        if self._is_h2_period(start, end):
            out["expertise_h2"] = self._build_h2(end)

        if compare is not None:
            rs, re = reference_period(start, end, compare)
            reference = self._analyse_period(rs, re)
            reference_facts = build_thermal_facts(reference)
            delta = compare_results(current, reference)
            current_period_ok = current.get("period_coverage", {}).get("strong_period_summary_allowed", False)
            reference_period_ok = reference.get("period_coverage", {}).get("strong_period_summary_allowed", False)
            strong_comparison_allowed = current_period_ok and reference_period_ok
            if not strong_comparison_allowed:
                delta = {key: None for key in delta}
            current_energy_ok = current.get("compressor_energy", {}).get("period_fact_allowed", False)
            reference_energy_ok = reference.get("compressor_energy", {}).get("period_fact_allowed", False)
            if not (current_energy_ok and reference_energy_ok):
                delta["compressor_energy_delta_kwh"] = None
            out["comparison"] = {
                "mode": compare,
                "period": {"start": rs.isoformat(), "end": re.isoformat()},
                "analysis": reference,
                "thermal_facts": reference_facts,
                "comparison_quality": {
                    "strong_comparison_allowed": strong_comparison_allowed,
                    "current_period_coverage": current.get("period_coverage", {}).get("coverage"),
                    "reference_period_coverage": reference.get("period_coverage", {}).get("coverage"),
                    "rule": "both_periods_require_strong_temporal_coverage",
                },
                "delta": delta,
                "comparison_facts": build_comparison_facts(delta),
            }
        return out
