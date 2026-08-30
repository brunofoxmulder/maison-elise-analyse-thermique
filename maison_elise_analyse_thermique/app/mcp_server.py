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


def _relative_day_period(
    now_value: datetime,
    tz: ZoneInfo,
    day: RelativeDay | None,
    start_time: str | None,
    end_time: str | None,
) -> tuple[datetime, datetime]:
    if day not in ("today", "yesterday"):
        raise ValueError("day is required when mode=relative_day")
    local_now = _normalize_now(now_value, tz)
    target_date = local_now.date() - timedelta(days=1 if day == "yesterday" else 0)
    start_clock = _parse_clock(start_time, "start_time")
    end_clock = _parse_clock(end_time, "end_time")
    start = datetime.combine(target_date, start_clock, tzinfo=tz)
    end = datetime.combine(target_date, end_clock, tzinfo=tz)
    if end <= start:
        raise ValueError("end_time must be after start_time on the selected day")
    return start, end


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
            "single_expertise_rule": (
                "short_response_and_full_report_must_be_created_from_the_same_reasoning_pass; "
                "never_answer_short_first_then_reanalyse_for_the_report"
            ),
            "publication_rule": (
                "for_the_current_hour_call_PublierRapportThermique_once_after_the_expertise; "
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
            "minimum_quality": "at_least_equivalent_to_historical_hourly_pyscript_llm_report",
            "sections": [
                "situation",
                "evolution",
                "energy",
                "explanations",
                "recommendations_volets_aeration_daikin",
                "outlook_h4",
                "vigilance",
                "conclusion_status",
            ],
            "epistemic_rule": "distinguish_fact_observation_hypothesis_uncertainty",
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

    expertise = result.get("expertise_h2")
    if not isinstance(expertise, dict):
        return
    analysis_contract = expertise.get("analysis_contract")
    if not isinstance(analysis_contract, dict):
        analysis_contract = {}
        expertise["analysis_contract"] = analysis_contract
    analysis_contract.update(
        {
            "shutter_position_rule": "cover_position_0_is_closed_100_is_open",
            "forecast_scope_rule": contract["forecast_horizon_rule"],
            "humidity_advice_rule": contract["humidity_rule"],
            "causality_rule": contract["causality_rule"],
            "expertise_then_publication_rule": contract["expertise_pipeline"],
        }
    )


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
            "Pour aujourd'hui/hier avec heures locales, utiliser mode=relative_day. Pour une date absolue historique, mode=explicit. "
            "Après un current_h2 réussi, réaliser UNE SEULE expertise complète à partir du JSON, en produisant dans la même réflexion "
            "la réponse courte et le rapport complet. Puis appeler OBLIGATOIREMENT PublierRapportThermique avec l'analysis_id retourné. "
            "Seulement après cette publication, répondre à l'utilisateur avec le short_response du rapport, sans refaire l'analyse. "
            "Qualité minimale du rapport complet : au moins équivalente au rapport horaire historique Pyscript rédigé par l'agent, "
            "avec Situation, Évolution, Énergie Daikin, Explications prudentes, Conseils Volets/Aération/Daikin, À venir H+4, Vigilance "
            "et Conclusion NORMAL/VIGILANCE/ALERTE. Les chiffres déterministes sont la source de vérité : ne pas recalculer. "
            "Convention volets 0 %=fermé, 100 %=ouvert. RH seule insuffisante pour aérer. Température Daikin terrasse = microclimat, "
            "jamais météo ni preuve de difficulté compresseur. Un extérieur plus frais n'implique pas automatiquement qu'il faut aérer. "
            "forecast_h4 est le seul horizon prospectif. Pour 'plus de détails', NE PAS rappeler AnalyseThermique : utiliser DernierRapportThermique."
        ),
    )
    def analyse_thermique(
        mode: AnalysisMode,
        start: datetime | None = None,
        end: datetime | None = None,
        compare: CompareMode | None = None,
        day: RelativeDay | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
    ) -> CallToolResult:
        nonlocal last_analysis_id, last_analysis_result

        received_start = start
        received_end = end
        received_compare = compare

        if mode == "current_h2":
            resolved_end = _normalize_now(now_provider(), tz)
            resolved_start = resolved_end - timedelta(hours=2)
            resolved_compare = None
        elif mode == "relative_day":
            resolved_start, resolved_end = _relative_day_period(
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

        _apply_interaction_contract(result)
        analysis_id = _analysis_id(mode, result)
        result["analysis_id"] = analysis_id
        result["expert_report_publication"] = {
            "required": mode == "current_h2",
            "status": "pending_expertise" if mode == "current_h2" else "optional",
            "next_tool": "PublierRapportThermique" if mode == "current_h2" else None,
            "rule": "publication_occurs_only_after_the_LLM_has_completed_the_single_expertise",
        }
        result["interaction_context"] = {
            "fresh_analysis": True,
            "voice_request_alias": "Analyse heure" if mode == "current_h2" else None,
        }
        last_analysis_id = analysis_id
        last_analysis_result = result
        record_result(result)
        return _tool_result(result)

    @mcp.tool(
        name="PublierRapportThermique",
        description=(
            "Étape 2 OBLIGATOIRE après AnalyseThermique mode=current_h2. À appeler UNE SEULE FOIS après avoir réalisé l'expertise complète. "
            "Tous les champs doivent provenir de la MÊME expertise : short_response est la synthèse vocale de ce rapport, pas une analyse séparée. "
            "analysis_id doit être recopié exactement depuis AnalyseThermique ; l'App refuse un rapport détaché de la dernière analyse. "
            "Le rapport doit être au minimum équivalent au Pyscript horaire expert : Situation, Évolution, Énergie Daikin, Explications prudentes, "
            "Volets, Aération, Daikin, À venir H+4, Vigilance, Conclusion avec statut NORMAL/VIGILANCE/ALERTE. "
            "Ne recalculer aucun chiffre et ne transformer aucune corrélation en cause certaine. Ce tool publie le rapport complet en notification "
            "persistante Home Assistant, mémorise exactement cette expertise pour 'plus de détails', puis renvoie short_response. "
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
    ) -> CallToolResult:
        if last_analysis_id is None or last_analysis_result is None:
            raise ValueError("no thermal analysis is awaiting an expert report")
        if analysis_id != last_analysis_id:
            raise ValueError("analysis_id does not match the latest thermal analysis")

        expertise = last_analysis_result.get("expertise_h2")
        primary_period = None
        if isinstance(expertise, dict):
            primary_period = expertise.get("primary_period")
        source_period = {
            "analysis_period": last_analysis_result.get("period"),
            "primary_period": primary_period,
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
        )
        report_store.save(report)
        delivery = notification_publisher.publish(report)
        rendered = render_expert_report(report)
        return _tool_result(
            {
                "analysis_id": analysis_id,
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
            "après une analyse thermique déjà publiée. Retourne EXACTEMENT le dernier rapport expert mémorisé. "
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
