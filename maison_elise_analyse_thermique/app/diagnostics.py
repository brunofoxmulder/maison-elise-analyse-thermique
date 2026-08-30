from __future__ import annotations

from collections import deque
from datetime import datetime
import json
import logging
from threading import Lock


_LOGGER = logging.getLogger(__name__)
_MAX_LINES = 40
_LINES: deque[str] = deque(maxlen=_MAX_LINES)
_LOCK = Lock()


def _append(kind: str, payload: dict) -> None:
    line = f"MCP_DIAG {kind} " + json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    with _LOCK:
        _LINES.append(line)
    _LOGGER.info(line)


def _analysis_snapshot(period: dict | None, analysis: dict | None) -> dict:
    analysis = analysis if isinstance(analysis, dict) else {}
    input_quality = analysis.get("input_quality")
    input_quality = input_quality if isinstance(input_quality, dict) else {}
    indoor = analysis.get("temperature_indoor")
    indoor = indoor if isinstance(indoor, dict) else {}
    outdoor = analysis.get("temperature_outdoor_reference")
    outdoor = outdoor if isinstance(outdoor, dict) else {}
    quality = analysis.get("quality")
    quality = quality if isinstance(quality, dict) else {}
    period_coverage = analysis.get("period_coverage")
    period_coverage = period_coverage if isinstance(period_coverage, dict) else {}

    return {
        "period": period,
        "raw_samples": analysis.get("raw_samples"),
        "samples_after_dedup": analysis.get("samples"),
        "near_duplicate_dropped_count": input_quality.get("near_duplicate_dropped_count"),
        "temperature_indoor_mean_c": indoor.get("mean"),
        "temperature_indoor_coverage": indoor.get("coverage"),
        "temperature_outdoor_mean_c": outdoor.get("mean"),
        "temperature_outdoor_coverage": outdoor.get("coverage"),
        "outdoor_temperature_suspect_count": quality.get("outdoor_temperature_suspect_count"),
        "outdoor_temperature_rejected_count": quality.get("outdoor_temperature_rejected_count"),
        "period_coverage": period_coverage.get("coverage"),
    }


def record_resolution(
    mode: str,
    received_start: datetime | None,
    received_end: datetime | None,
    received_compare: str | None,
    resolved_start: datetime,
    resolved_end: datetime,
    resolved_compare: str | None,
) -> None:
    _append(
        "resolution",
        {
            "mode": mode,
            "received_start": received_start.isoformat() if received_start else None,
            "received_end": received_end.isoformat() if received_end else None,
            "received_compare": received_compare,
            "resolved_start": resolved_start.isoformat(),
            "resolved_end": resolved_end.isoformat(),
            "resolved_compare": resolved_compare,
        },
    )


def record_request(start: datetime, end: datetime, compare: str | None) -> None:
    _append(
        "request",
        {
            "start": start.isoformat(),
            "end": end.isoformat(),
            "compare": compare,
        },
    )


def record_result(result: dict) -> None:
    result = result if isinstance(result, dict) else {}
    comparison = result.get("comparison")
    comparison = comparison if isinstance(comparison, dict) else {}

    _append(
        "current_analysis",
        _analysis_snapshot(result.get("period"), result.get("analysis")),
    )
    if comparison:
        _append(
            "reference_analysis",
            _analysis_snapshot(comparison.get("period"), comparison.get("analysis")),
        )

    _append(
        "result",
        {
            "period": result.get("period"),
            "comparison_mode": comparison.get("mode"),
            "comparison_period": comparison.get("period"),
            "delta": comparison.get("delta"),
        },
    )


def record_error(start: datetime, end: datetime, compare: str | None, exc: Exception) -> None:
    _append(
        "error",
        {
            "start": start.isoformat(),
            "end": end.isoformat(),
            "compare": compare,
            "error_type": type(exc).__name__,
            "message": str(exc),
        },
    )


def diagnostics_text() -> str:
    with _LOCK:
        if not _LINES:
            return "Aucun appel MCP AnalyseThermique enregistré depuis le démarrage de l'App."
        return "\n".join(_LINES)


def clear_diagnostics() -> None:
    with _LOCK:
        _LINES.clear()
