from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from threading import Lock
from typing import Literal


ExpertStatus = Literal["NORMAL", "VIGILANCE", "ALERTE"]


def _clean(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} is required")
    return value.strip()


def build_expert_report(
    *,
    analysis_id: str,
    status: ExpertStatus,
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
    source_period: dict | None = None,
) -> dict:
    if status not in ("NORMAL", "VIGILANCE", "ALERTE"):
        raise ValueError("status must be NORMAL, VIGILANCE or ALERTE")
    report = {
        "analysis_id": _clean(analysis_id, "analysis_id"),
        "status": status,
        "short_response": _clean(short_response, "short_response"),
        "sections": {
            "situation": _clean(situation, "situation"),
            "evolution": _clean(evolution, "evolution"),
            "energy": _clean(energy, "energy"),
            "explanations": _clean(explanations, "explanations"),
            "recommendations": {
                "shutters": _clean(shutters_advice, "shutters_advice"),
                "ventilation": _clean(ventilation_advice, "ventilation_advice"),
                "daikin": _clean(daikin_advice, "daikin_advice"),
            },
            "outlook": _clean(outlook, "outlook"),
            "vigilance": _clean(vigilance, "vigilance"),
            "conclusion": _clean(conclusion, "conclusion"),
        },
        "source_period": deepcopy(source_period) if isinstance(source_period, dict) else None,
    }
    return report


def render_expert_report(report: dict) -> str:
    sections = report["sections"]
    recommendations = sections["recommendations"]
    return "\n\n".join(
        [
            "## Situation\n" + sections["situation"],
            "## Évolution par rapport à l’heure précédente\n" + sections["evolution"],
            "## ⚡ Énergie Daikin\n" + sections["energy"],
            "## Explications prudentes\n" + sections["explanations"],
            "## Conseil pour les 2 à 4 prochaines heures\n"
            + "\n".join(
                [
                    f"- **Volets :** {recommendations['shutters']}",
                    f"- **Aération :** {recommendations['ventilation']}",
                    f"- **Daikin :** {recommendations['daikin']}",
                    f"- **À venir :** {sections['outlook']}",
                ]
            ),
            "## Points de vigilance\n" + sections["vigilance"],
            f"## Conclusion\n**{report['status']}.** {sections['conclusion']}",
        ]
    )


def notification_title(report: dict) -> str:
    return f"Analyse thermique — heure · {report['status']}"


class ExpertReportStore:
    """Mémoire courte du dernier rapport expert publié.

    Elle permet à « plus de détails » de restituer exactement la même expertise,
    sans relancer le calcul thermique ni demander au LLM de refaire l’analyse.
    """

    def __init__(self) -> None:
        self._last_report: dict | None = None
        self._lock = Lock()

    def save(self, report: dict) -> None:
        with self._lock:
            stored = deepcopy(report)
            stored["stored_at"] = datetime.now().astimezone().isoformat()
            self._last_report = stored

    def get(self) -> dict | None:
        with self._lock:
            return deepcopy(self._last_report)
