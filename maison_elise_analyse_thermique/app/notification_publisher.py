from __future__ import annotations

from threading import Lock

import httpx

from .expert_report import notification_title, render_expert_report


DEFAULT_NOTIFICATION_ID = "maison_elise_analyse_thermique"


class UnavailableNotificationPublisher:
    def __init__(self, reason: str = "home_assistant_api_unavailable") -> None:
        self.reason = reason

    def publish(self, report: dict) -> dict:
        return {
            "enabled": False,
            "status": "disabled",
            "reason": self.reason,
        }


class HomeAssistantNotificationPublisher:
    """Publie dans HA le rapport expert déjà rédigé par le LLM.

    L'App ne rédige pas l'expertise. Elle reçoit un rapport structuré lié à une
    analyse déterministe, le met en forme et appelle uniquement
    ``persistent_notification.create``. Aucun équipement n'est commandé.
    """

    def __init__(
        self,
        token: str,
        *,
        notification_id: str = DEFAULT_NOTIFICATION_ID,
        base_url: str = "http://supervisor/core/api",
        timeout_seconds: float = 5.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if not token:
            raise ValueError("Home Assistant token is required")
        if not isinstance(notification_id, str) or not notification_id.strip():
            raise ValueError("notification_id is required")
        self.token = token
        self.notification_id = notification_id.strip()
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = float(timeout_seconds)
        self.transport = transport
        self._last_analysis_id: str | None = None
        self._lock = Lock()

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

    def publish(self, report: dict) -> dict:
        analysis_id = report.get("analysis_id")
        if not isinstance(analysis_id, str) or not analysis_id:
            raise ValueError("expert report analysis_id is required")

        with self._lock:
            if self._last_analysis_id == analysis_id:
                return {
                    "enabled": True,
                    "status": "duplicate_skipped",
                    "service": "persistent_notification.create",
                    "notification_id": self.notification_id,
                    "analysis_id": analysis_id,
                }

        payload = {
            "title": notification_title(report),
            "message": render_expert_report(report),
            "notification_id": self.notification_id,
        }
        try:
            with httpx.Client(timeout=self.timeout_seconds, transport=self.transport) as client:
                response = client.post(
                    f"{self.base_url}/services/persistent_notification/create",
                    headers=self._headers(),
                    json=payload,
                )
                response.raise_for_status()
        except Exception as exc:
            return {
                "enabled": True,
                "status": "error",
                "service": "persistent_notification.create",
                "notification_id": self.notification_id,
                "analysis_id": analysis_id,
                "error_type": type(exc).__name__,
            }

        with self._lock:
            self._last_analysis_id = analysis_id
        return {
            "enabled": True,
            "status": "sent",
            "service": "persistent_notification.create",
            "notification_id": self.notification_id,
            "analysis_id": analysis_id,
        }
