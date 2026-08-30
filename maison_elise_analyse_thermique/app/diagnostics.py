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
    comparison = result.get("comparison") if isinstance(result, dict) else None
    comparison = comparison if isinstance(comparison, dict) else {}
    _append(
        "result",
        {
            "period": result.get("period") if isinstance(result, dict) else None,
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
