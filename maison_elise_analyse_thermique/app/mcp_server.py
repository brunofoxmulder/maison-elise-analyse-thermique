from __future__ import annotations

import hashlib
import json
from datetime import datetime, time, timedelta
import re
from typing import Literal
from zoneinfo import ZoneInfo

from mcp.server.fastmcp import FastMCP
from mcp.types import CallToolResult, TextContent

from .assist_brief import build_assist_brief_facts
from .diagnostics import (
    record_error,
    record_request,
    record_resolution,
    record_result,
)
from .expert_report import (
    ExpertReportStore,
    ReportProfile,
    build_expert_report,
    render_expert_report,
)
from .notification_publisher import UnavailableNotificationPublisher
from .service import ThermalAnalysisService


AnalysisMode = Literal["current_h2", "relative_day", "explicit"]
RelativeDay = Literal["today", "yesterday"]
CompareMode = Literal[
    "previous_period",
    "previous_hour",
    "previous_day",
    "j-1",
    "previous_week",
    "s-1",
    "previous_month",
    "m-1",
]
ReportStatus = Literal["NORMAL", "VIGILANCE", "ALERTE"]

_TIME_RE = re.compile(r"^(?P<hour>\d{1,2})(?::(?P<minute>\d{2}))?$")
_DATE_DMY_RE = re.compile(
    r"^(?P<day>\d{1,2})[-/](?P<month>\d{1,2})(?:[-/](?P<year>\d{4}))?$"
)
_DATE_ISO_RE = re.compile(r"^(?P<year>\d{4})-(?P<month>\d{1,2})-(?P<day>\d{1,2})$")


def _parse_clock(value: str, field_name: str) -> time:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} is required when mode=relative_day")
    match = _TIME_RE.fullmatch(value.strip())
    if not match:
        raise ValueError(f"{field_name} must use HH:MM or HH")
    hour = int(match.group("hour"))
    minute = int(match.group("minute") or 0)
    if hour > 23 or minute > 59:
        raise ValueError(f"{field_name} is not a valid local time")
    return time(hour=hour, minute=minute)


def _normalize_now(now_value: datetime, tz: ZoneInfo) -> datetime:
    if now_value.tzinfo is None or now_value.utcoffset() is None:
        return now_value.replace(tzinfo=tz)
    return now_value.astimezone(tz)


def _resolve_day_selector(local_now: datetime, day: str | None) -> tuple[datetime, dict]:
    selector = (day or "today").strip().lower()
    year_source = "relative"

    if selector == "today":
        target_year = local_now.year
        target_month = local_now.month
        target_day = local_now.day
    elif selector == "yesterday":
        target = local_now.date() - timedelta(days=1)
        target_year, target_month, target_day = target.year, target.month, target.day
    else:
        match = _DATE_DMY_RE.fullmatch(selector)
        if match:
            target_day = int(match.group("day"))
            target_month = int(match.group("month"))
            explicit_year = match.group("year")
            if explicit_year is None:
                target_year = local_now.year
                year_source = "current_year_default"
            else:
                target_year = int(explicit_year)
                year_source = "explicit"
        else:
            match = _DATE_ISO_RE.fullmatch(selector)
            if not match:
                raise ValueError(
                    "day must be today, yesterday, DD-MM, DD-MM-YYYY or YYYY-MM-DD"
                )
            target_year = int(match.group("year"))
            target_month = int(match.group("month"))
            target_day = int(match.group("day"))
            year_source = "explicit"

    try:
        target_start = datetime(target_year, target_month, target_day, tzinfo=local_now.tzinfo)
    except ValueError as exc:
        raise ValueError("day is not a valid calendar date") from exc

    if target_start.date() > local_now.date():
        raise ValueError("future thermal days cannot be analysed")

    resolution = {
        "received_selector": day,
        "normalized_selector": selector,
        "resolved_date": target_start.date().isoformat(),
        "year_source": year_source,
        "current_year_default_rule": (
            "when_the_user_omits_the_year_the_App_uses_the_current_local_calendar_year"
        ),
        "historical_year_rule": "an_older_year_must_be_explicitly_requested",
    }
    return target_start, resolution


def _relative_day_period(
    now_value: datetime,
    tz: ZoneInfo,
    day: str | None,
    start_time: str | None,
    end_time: str | None,
) -> tuple[datetime, datetime, dict, bool]:
    local_now = _normalize_now(now_value, tz)
    target_start, resolution = _resolve_day_selector(local_now, day)

    if (start_time is None) != (end_time is None):
        raise ValueError("start_time and end_time must either both be supplied or both be omitted")

    full_day_profile = start_time is None and end_time is None
    if full_day_profile:
        start = target_start
        if target_start.date() == local_now.date():
            end = local_now
            completeness = "today_so_far"
        else:
            next_date = target_start.date() + timedelta(days=1)
            end = datetime.combine(next_date, time.min, tzinfo=tz)
            completeness = "completed_day"
    else:
        start_clock = _parse_clock(start_time, "start_time")
        end_clock = _parse_clock(end_time, "end_time")
        start = datetime.combine(target_start.date(), start_clock, tzinfo=tz)
        end = datetime.combine(target_start.date(), end_clock, tzinfo=tz)
        if end <= start:
            raise ValueError("end_time must be after start_time on the selected day")
        completeness = "explicit_intraday_window"

    if end <= start:
        raise ValueError("selected day has no elapsed analysis interval yet")

    resolution.update(
        {
            "full_day_profile": full_day_profile,
            "completeness": completeness,
            "resolved_start": start.isoformat(),
            "resolved_end": end.isoformat(),
        }
    )
    return start, end, resolution, full_day_profile


def _normalize_compare(
    compare: CompareMode | None,
    start: datetime,
    end: datetime,
) -> str | None:
    if compare != "previous_hour":
        return compare
    duration_minutes = (end - start).total_seconds() / 60.0
    if not 55.0 <= duration_minutes <= 65.0:
        raise ValueError(
            "previous_hour is only valid for an explicit or relative period of about one hour"
        )
    return "previous_period"


def _tool_result(result: dict) -> CallToolResult:
    return CallToolResult(
        content=[
            TextContent(
                type="text",
                text=json.dumps(result, ensure_ascii=False, separators=(",", ":")),
            )
        ],
        structuredContent=result,
    )


def _analysis_id(mode: AnalysisMode, result: dict) -> str:
    expertise = result.get("expertise_h2")
    observed_end = None
    if isinstance(expertise, dict):
        observed_end = (expertise.get("data_window") or {}).get("observed_end")
    payload = {
        "mode": mode,
        "period": result.get("period"),
        "observed_end": observed_end,
        "comparison_mode": (result.get("comparison") or {}).get("mode"),
    }
    digest = hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()[:20]
    return f"thermal-{digest}"


def _apply_interaction_contract(result: dict) -> None:
    brief = build_assist_brief_facts(result)
    if brief is not None:
        result["assist_brief_facts"] = brief

    contract = {
        "expertise_pipeline": {
            "principle": "one_app_calculation_then_one_llm_expertise_then_two_outputs",
            "required_order_for_current_hour": [
                "AnalyseThermique",
                "one_complete_expertise",
                "PublierRapportThermique",
                "reply_with_short_response",
            ],
            "required_order_for_full_day": [
                "AnalyseThermique",
                "one_complete_expertise",
                "PublierRapportThermique_profile_day",
                "reply_with_short_response",
            ],
            "single_expertise_rule": (
                "short_response_and_full_report_must_be_created_from_the_same_reasoning_pass; "
                "never_answer_short_first_then_reanalyse_for_the_report"
            ),
            "publication_rule": (
                "for_the_current_hour_or_a_full_day_call_PublierRapportThermique_once_after_the_expertise; "
                "the_App_must_not_publish_raw_deterministic_facts_before_expertise"
            ),
        },
        "voice_short_response": {
            "order": ["constat", "analyse", "preconisation", "a_venir"],
            "max_sentences": 5,
            "plain_text_no_markdown_headings": True,
            "internal_terms_to_hide": ["H-2", "H−2", "current_h2", "expertise_h2"],
            "fact_source_rule": (
                "when_assist_brief_facts_is_present_use_it_as_the_primary_fact_source_for_the_short_response; "
                "never_use_top_level_two_hour_aggregate_durations_as_last_hour_facts"
            ),
            "recommendation_rule": (
                "recommendation_is_optional; never_force_an_action; "
                "prefer_no_action_needed_when_no_useful_action_is_supported_by_the_facts"
            ),
        },
        "full_expert_report": {
            "minimum_quality": "at_least_equivalent_to_historical_pyscript_llm_report_for_the_selected_profile",
            "hour_sections": [
                "situation",
                "evolution",
                "energy",
                "explanations",
                "recommendations_volets_aeration_daikin",
                "outlook_h4",
                "vigilance",
                "conclusion_status",
            ],
            "day_sections": [
                "situation",
                "setpoints_and_tracking",
                "day_evolution",
                "energy",
                "explanations",
                "recommendations_volets_aeration_daikin",
                "vigilance",
                "conclusion_status",
            ],
            "epistemic_rule": "distinguish_fact_observation_hypothesis_uncertainty",
        },
        "day_profile_rule": {
            "setpoints": (
                "use_recorded_setpoint_profiles; analyse_the_two_dominant_requested_temperatures_separately_when_two_are_present; "
                "never_replace_them_with_one_average_and_never_hardcode_19_21_or_any_other_setpoint"
            ),
            "season": "apply_the_same_rule_in_cooling_and_heating_modes",
            "historical_scope": (
                "for_a_completed_historical_day_do_not_invent_advice_for_today_or_future_weather; "
                "describe_the_day_and_only_add_later_actions_if_the_user_explicitly_asked_for_them"
            ),
        },
        "detail_follow_up": {
            "user_phrases": ["donne-moi le détail", "donne plus de détails", "détaille", "plus de détails"],
            "tool": "DernierRapportThermique",
            "reuse_same_expertise": True,
            "rule": (
                "never_call_AnalyseThermique_and_never_redo_the_expertise_for_a_detail_follow_up; "
                "retrieve_and_speak_the_already_published_full_report"
            ),
        },
        "shutter_position_semantics": {
            "0": "fully_closed",
            "100": "fully_open",
            "intermediate": "percentage_open",
            "rule": (
                "never_invert_cover_position_semantics; "
                "never_recommend_closing_or_opening_without_relevant_solar_facts"
            ),
        },
        "humidity_rule": (
            "relative_humidity_alone_is_not_a_basis_for_ventilation_or_dehumidification_advice; "
            "use_temperature_and_absolute_moisture_context_together"
        ),
        "causality_rule": (
            "do_not_say_outdoor_temperature_explains_continuous_cooling_by_itself; "
            "do_not_turn_correlations_into_proven_causes"
        ),
        "forecast_horizon_rule": (
            "forecast_h4_is_the_only_prospective_horizon_provided_by_this_H2_result; "
            "never_mention_tomorrow_or_any_time_after_the_last_forecast_h4_point_unless_the_user_explicitly_requests_another_forecast"
        ),
    }
    result["interaction_contract"] = contract

    expertise_h2 = result.get("expertise_h2")
    if isinstance(expertise_h2, dict):
        analysis_contract = expertise_h2.get("analysis_contract")
        if not isinstance(analysis_contract, dict):
            analysis_contract = {}
            expertise_h2["analysis_contract"] = analysis_contract
        analysis_contract.update(
            {
                "shutter_position_rule": "cover_position_0_is_closed_100_is_open",
                "forecast_scope_rule": contract["forecast_horizon_rule"],
                "humidity_advice_rule": contract["humidity_rule"],
                "causality_rule": contract["causality_rule"],
                "expertise_then_publication_rule": contract["expertise_pipeline"],
            }
        )

    expertise_day = result.get("expertise_day")
    if isinstance(expertise_day, dict):
        expertise_day["analysis_contract"] = {
            "profile": "day",
            "setpoint_rule": contract["day_profile_rule"]["setpoints"],
            "season_rule": contract["day_profile_rule"]["season"],
            "historical_scope_rule": contract["day_profile_rule"]["historical_scope"],
            "shutter_position_rule": "cover_position_0_is_closed_100_is_open",
            "humidity_advice_rule": contract["humidity_rule"],
            "causality_rule": contract["causality_rule"],
            "expertise_then_publication_rule": contract["expertise_pipeline"],
        }


def build_mcp_server(
    service: ThermalAnalysisService,
    timezone: str = "Europe/Paris",
    now_provider=None,
    notification_publisher=None,
) -> FastMCP:
    """Build the MCP facade around the deterministic thermal service."""
    tz = ZoneInfo(timezone)
    if now_provider is None:
        now_provider = lambda: datetime.now(tz)
    if notification_publisher is None:
        notification_publisher = UnavailableNotificationPublisher()

    last_analysis_id: str | None = None
    last_analysis_result: dict | None = None
    report_store = ExpertReportStore()

    mcp = FastMCP(
        name="Maison Élise — Analyse thermique",
        instructions=(
            "Serveur thermique : l'App calcule les faits, le LLM réalise une seule expertise, "
            "puis publie cette même expertise dans Home Assistant et en extrait la réponse courte."
        ),
        host="0.0.0.0",
        stateless_http=True,
        json_response=True,
    )

    @mcp.tool(
        name="AnalyseThermique",
        description=(
            "Étape 1 du flux thermique. Calcule uniquement les faits déterministes : ne publie PAS de notification. "
            "Pour 'Analyse heure', 'analyse de l'heure', 'analyse actuelle' ou équivalent, utiliser mode=current_h2 ; "
            "l'App résout elle-même les deux dernières heures avec son horloge Europe/Paris, sans start/end calculés par le LLM. "
            "Pour 'Analyse jour', 'analyse de la journée', 'analyse d'hier' ou une date comme '20 août', utiliser mode=relative_day SANS start_time/end_time. "
            "Le champ day accepte today, yesterday, DD-MM, DD-MM-YYYY ou YYYY-MM-DD. Si l'utilisateur ne dit PAS l'année, transmettre DD-MM sans année : "
            "l'App applique déterministiquement l'année locale en cours. Une année antérieure ne doit être envoyée que si l'utilisateur l'a explicitement dite. "
            "Pour aujourd'hui/hier entre deux heures, utiliser mode=relative_day avec start_time et end_time. Pour une période absolue libre, mode=explicit. "
            "Après un current_h2 ou une journée complète réussie, réaliser UNE SEULE expertise complète à partir du JSON, en produisant dans la même réflexion "
            "la réponse courte et le rapport complet. Puis appeler OBLIGATOIREMENT PublierRapportThermique avec l'analysis_id retourné. "
            "Pour une journée complète, appeler PublierRapportThermique avec profile=day et remplir setpoints à partir de setpoint_profiles : "
            "analyser séparément les deux températures demandées enregistrées quand elles sont présentes, en mode froid comme en chauffage, sans les moyenner en une seule consigne. "
            "Seulement après cette publication, répondre à l'utilisateur avec le short_response du rapport, sans refaire l'analyse. "
            "Qualité minimale du rapport complet : au moins équivalente au rapport historique Pyscript rédigé par l'agent. "
            "Convention volets 0 %=fermé, 100 %=ouvert. RH seule insuffisante pour aérer. Température Daikin terrasse = microclimat, "
            "jamais météo ni preuve de difficulté compresseur. Un extérieur plus frais n'implique pas automatiquement qu'il faut aérer. "
            "Ne jamais transformer une corrélation en cause certaine. Pour 'plus de détails', NE PAS rappeler AnalyseThermique : utiliser DernierRapportThermique."
        ),
    )
    def analyse_thermique(
        mode: AnalysisMode,
        start: datetime | None = None,
        end: datetime | None = None,
        compare: CompareMode | None = None,
        day: str | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
    ) -> CallToolResult:
        nonlocal last_analysis_id, last_analysis_result

        received_start = start
        received_end = end
        received_compare = compare
        date_resolution = None
        full_day_profile = False

        if mode == "current_h2":
            resolved_end = _normalize_now(now_provider(), tz)
            resolved_start = resolved_end - timedelta(hours=2)
            resolved_compare = None
        elif mode == "relative_day":
            resolved_start, resolved_end, date_resolution, full_day_profile = _relative_day_period(
                now_provider(), tz, day, start_time, end_time
            )
            resolved_compare = _normalize_compare(compare, resolved_start, resolved_end)
        else:
            if start is None or end is None:
                raise ValueError("start and end are required when mode=explicit")
            resolved_start = start
            resolved_end = end
            resolved_compare = _normalize_compare(compare, resolved_start, resolved_end)

        record_resolution(
            mode,
            received_start,
            received_end,
            received_compare,
            resolved_start,
            resolved_end,
            resolved_compare,
        )
        record_request(resolved_start, resolved_end, resolved_compare)
        try:
            result = service.analyse(
                resolved_start,
                resolved_end,
                resolved_compare,
            )
        except Exception as exc:
            record_error(resolved_start, resolved_end, resolved_compare, exc)
            raise

        if date_resolution is not None:
            result["date_resolution"] = date_resolution
        if full_day_profile:
            result["expertise_day"] = {
                "profile": "day",
                "period": result.get("period"),
                "date_resolution": date_resolution,
                "setpoint_profiles": result.get("setpoint_profiles"),
                "setpoint_interpretation_rule": (
                    "use_the_recorded_requested_temperatures_and_their_time_ranges; "
                    "when_two_are_present_analyse_each_separately_instead_of_using_one_average"
                ),
            }

        _apply_interaction_contract(result)
        analysis_id = _analysis_id(mode, result)
        result["analysis_id"] = analysis_id
        publication_required = mode == "current_h2" or full_day_profile
        publication = {
            "required": publication_required,
            "status": "pending_expertise" if publication_required else "optional",
            "next_tool": "PublierRapportThermique" if publication_required else None,
            "rule": "publication_occurs_only_after_the_LLM_has_completed_the_single_expertise",
        }
        if full_day_profile:
            publication["profile"] = "day"
        result["expert_report_publication"] = publication
        result["interaction_context"] = {
            "fresh_analysis": True,
            "voice_request_alias": (
                "Analyse jour" if full_day_profile else ("Analyse heure" if mode == "current_h2" else None)
            ),
        }
        last_analysis_id = analysis_id
        last_analysis_result = result
        record_result(result)
        return _tool_result(result)

    @mcp.tool(
        name="PublierRapportThermique",
        description=(
            "Étape 2 OBLIGATOIRE après AnalyseThermique mode=current_h2 ou après une journée complète. À appeler UNE SEULE FOIS après avoir réalisé l'expertise complète. "
            "Tous les champs doivent provenir de la MÊME expertise : short_response est la synthèse vocale de ce rapport, pas une analyse séparée. "
            "analysis_id doit être recopié exactement depuis AnalyseThermique ; l'App refuse un rapport détaché de la dernière analyse. "
            "Pour l'heure, laisser profile=hour. Pour une journée complète, utiliser profile=day et fournir setpoints : cette section doit décrire les consignes enregistrées, "
            "leurs plages et le suivi thermique, en distinguant les deux températures demandées dominantes quand deux sont présentes, en froid comme en chauffage. "
            "Le rapport doit être au minimum équivalent au Pyscript expert : Situation, Consignes et suivi pour le jour, Évolution, Énergie Daikin, Explications prudentes, "
            "Volets, Aération, Daikin, Vigilance et Conclusion NORMAL/VIGILANCE/ALERTE. Ne recalculer aucun chiffre et ne transformer aucune corrélation en cause certaine. "
            "Ce tool publie le rapport complet en notification persistante Home Assistant, mémorise exactement cette expertise pour 'plus de détails', puis renvoie short_response. "
            "Après son succès, répondre à l'utilisateur avec short_response uniquement, en quelques phrases."
        ),
    )
    def publier_rapport_thermique(
        analysis_id: str,
        status: ReportStatus,
        short_response: str,
        situation: str,
        evolution: str,
        energy: str,
        explanations: str,
        shutters_advice: str,
        ventilation_advice: str,
        daikin_advice: str,
        outlook: str,
        vigilance: str,
        conclusion: str,
        profile: ReportProfile = "hour",
        setpoints: str | None = None,
    ) -> CallToolResult:
        if last_analysis_id is None or last_analysis_result is None:
            raise ValueError("no thermal analysis is awaiting an expert report")
        if analysis_id != last_analysis_id:
            raise ValueError("analysis_id does not match the latest thermal analysis")
        if profile == "day" and not isinstance(last_analysis_result.get("expertise_day"), dict):
            raise ValueError("profile=day requires the latest analysis to be a full day profile")

        expertise = last_analysis_result.get("expertise_h2")
        primary_period = None
        if isinstance(expertise, dict):
            primary_period = expertise.get("primary_period")
        source_period = {
            "analysis_period": last_analysis_result.get("period"),
            "primary_period": primary_period,
            "date_resolution": last_analysis_result.get("date_resolution"),
        }
        report = build_expert_report(
            analysis_id=analysis_id,
            status=status,
            short_response=short_response,
            situation=situation,
            evolution=evolution,
            energy=energy,
            explanations=explanations,
            shutters_advice=shutters_advice,
            ventilation_advice=ventilation_advice,
            daikin_advice=daikin_advice,
            outlook=outlook,
            vigilance=vigilance,
            conclusion=conclusion,
            source_period=source_period,
            profile=profile,
            setpoints=setpoints,
        )
        report_store.save(report)
        delivery = notification_publisher.publish(report)
        rendered = render_expert_report(report)
        return _tool_result(
            {
                "analysis_id": analysis_id,
                "profile": profile,
                "status": status,
                "publication": delivery,
                "short_response": report["short_response"],
                "full_report": rendered,
                "instruction": "reply_to_user_with_short_response_only_unless_the_user_asked_for_detail",
            }
        )

    @mcp.tool(
        name="DernierRapportThermique",
        description=(
            "À utiliser uniquement quand l'utilisateur demande 'plus de détails', 'donne-moi le détail', 'détaille' ou équivalent "
            "après une analyse thermique déjà publiée. Retourne EXACTEMENT le dernier rapport expert mémorisé, heure ou jour. "
            "Ne pas appeler AnalyseThermique, ne pas recalculer et ne pas refaire une expertise. Lire/restituer full_report."
        ),
    )
    def dernier_rapport_thermique() -> CallToolResult:
        report = report_store.get()
        if report is None:
            raise ValueError("no expert thermal report has been published in this App process")
        return _tool_result(
            {
                "analysis_id": report["analysis_id"],
                "profile": report.get("profile", "hour"),
                "status": report["status"],
                "short_response": report["short_response"],
                "full_report": render_expert_report(report),
                "reused_previous_expertise": True,
                "recalculation": False,
                "new_expertise": False,
                "new_notification": False,
            }
        )

    return mcp