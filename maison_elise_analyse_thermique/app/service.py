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
from .weather_forecast import UnavailableWeatherForecastProvider


class ThermalAnalysisService:
    def __init__(self, source, config=None, forecast_provider=None):
        self.source = source
        self.config = config or AnalysisConfig()
        self.forecast_provider = forecast_provider or UnavailableWeatherForecastProvider()

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

    def _forecast_h4(self, end):
        try:
            return self.forecast_provider.get_h4(end)
        except Exception:
            # Forecast context must never make the deterministic retrospective
            # analysis fail. Missing weather is exposed as uncertainty instead.
            return UnavailableWeatherForecastProvider("forecast_provider_error").get_h4(end)

    def _build_h2(self, end):
        last_start = end - timedelta(hours=1)
        previous_start = end - timedelta(hours=2)

        previous_analysis, previous_samples = self._prepare_period(
            previous_start,
            last_start,
        )
        last_analysis, last_samples = self._prepare_period(last_start, end)

        expertise = build_h2_expertise(
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
        expertise["forecast_h4"] = self._forecast_h4(end)
        expertise["analysis_contract"].update(
            {
                "prompt_version": "h2-expert-v1",
                "h2_result_rule": (
                    "when_expertise_h2_is_present_use_it_as_the_primary_H2_material; "
                    "top_level_analysis_is_the_legacy_two_hour_aggregate_and_is_not_the_primary_H2_summary"
                ),
                "quality_rule": (
                    "if_hourly_coverage_or_data_quality_is_insufficient_weaken_the_conclusion_explicitly; "
                    "never_fill_missing_measurements_by_guessing"
                ),
                "evidence_rule": (
                    "distinguish_fact_observation_hypothesis_and_uncertainty; "
                    "correlation_or_simultaneity_is_not_proven_causality"
                ),
                "setpoint_transition_rule": (
                    "after_an_active_setpoint_change_treat_a_temporary_temperature_gap_as_possible_inertia; "
                    "do_not_call_it_bad_regulation_without_supporting_evidence"
                ),
                "compressor_rule": (
                    "assess_daikin_with_hvac_action_frequency_energy_indoor_temperature_active_setpoint_"
                    "reliable_outdoor_temperature_openings_and_solar_context_together"
                ),
                "dehumidification_rule": (
                    "if_indoor_temperature_is_near_setpoint_while_cooling_continues_and_humidity_is_high_"
                    "dehumidification_or_modulation_may_be_compatible_explanations_but_are_not_proven_causes"
                ),
                "ventilation_context_rule": (
                    "ventilation_can_renew_air_or_change_temperature_or_moisture_and_can_temporarily_help_daikin; "
                    "apply_the_same_temperature_and_moisture_reasoning_in_cooling_and_heating_modes"
                ),
                "solar_rule": (
                    "distinguish_solar_geometry_bright_sky_and_effective_sun; "
                    "lux_alone_does_not_prove_direct_solar_heat_and_simultaneous_shutter_changes_do_not_prove_causality"
                ),
                "forecast_rule": (
                    "h4_forecast_is_prospective_context_not_a_certainty; "
                    "missing_forecast_must_be_reported_as_uncertainty_and_never_invented"
                ),
                "wind_rule": (
                    "outdoor_wind_can_inform_ventilation_potential_but_never_proves_indoor_airflow"
                ),
                "response_contract": {
                    "status": ["NORMAL", "VIGILANCE", "ALERTE"],
                    "status_rules": {
                        "NORMAL": "coherent_operation_without_significant_drift_found",
                        "VIGILANCE": "measured_evolution_or_combination_of_facts_to_watch_without_proven_serious_anomaly",
                        "ALERTE": "use_only_for_clearly_abnormal_or_concerning_measured_situations_and_do_not_be_alarmist",
                    },
                    "sections": [
                        "Situation",
                        "Évolution entre les deux heures",
                        "Explications prudentes",
                        "Conseil pour les 2 à 4 prochaines heures",
                        "Points de vigilance",
                        "Conclusion",
                    ],
                    "advice_labels": ["Volets", "Aération", "Daikin"],
                    "assist_voice_rule": (
                        "for_a_normal_voice_answer_keep_only_three_or_four_useful_conclusions; "
                        "expand_only_when_the_user_requests_detail"
                    ),
                },
            }
        )
        return expertise

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
