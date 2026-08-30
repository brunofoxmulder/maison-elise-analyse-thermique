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
    analyse déterministe, le met en forme et appelle ``persistent_notification.create``.
    Si ``mail_service`` est configuré, elle transmet ensuite exactement le même
    rapport au service ``notify.*`` de Home Assistant, par exemple un notifier
    SMTP déjà géré par HA. L'App ne contient aucun serveur, mot de passe ni
    destinataire SMTP et ne commande aucun équipement.
    """

    def __init__(
        self,
        token: str,
        *,
        notification_id: str = DEFAULT_NOTIFICATION_ID,
        mail_service: str = "",
        base_url: str = "http://supervisor/core/api",
        timeout_seconds: float = 5.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if not token:
            raise ValueError("Home Assistant token is required")
        if not isinstance(notification_id, str) or not notification_id.strip():
            raise ValueError("notification_id is required")
        if not isinstance(mail_service, str):
            raise ValueError("mail_service must be a string")
        normalized_mail_service = mail_service.strip()
        if normalized_mail_service and not normalized_mail_service.startswith("notify."):
            raise ValueError("mail_service must use a Home Assistant notify.* service")

        self.token = token
        self.notification_id = notification_id.strip()
        self.mail_service = normalized_mail_service
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

    def _publish_mail(self, client: httpx.Client, report: dict, rendered: str) -> dict:
        if not self.mail_service:
            return {
                "enabled": False,
                "status": "disabled",
                "reason": "mail_service_not_configured",
            }

        service_name = self.mail_service.split(".", 1)[1]
        payload = {
            "title": notification_title(report),
            "message": rendered,
        }
        try:
            response = client.post(
                f"{self.base_url}/services/notify/{service_name}",
                headers=self._headers(),
                json=payload,
            )
            response.raise_for_status()
        except Exception as exc:
            return {
                "enabled": True,
                "status": "error",
                "service": self.mail_service,
                "error_type": type(exc).__name__,
            }
        return {
            "enabled": True,
            "status": "sent",
            "service": self.mail_service,
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

        rendered = render_expert_report(report)
        payload = {
            "title": notification_title(report),
            "message": rendered,
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
                mail_delivery = self._publish_mail(client, report, rendered)
        except Exception as exc:
            return {
                "enabled": True,
                "status": "error",
                "service": "persistent_notification.create",
                "notification_id": self.notification_id,
                "analysis_id": analysis_id,
                "error_type": type(exc).__name__,
                "mail": {
                    "enabled": bool(self.mail_service),
                    "status": "not_attempted",
                    "reason": "persistent_notification_failed",
                },
            }

        with self._lock:
            self._last_analysis_id = analysis_id
        return {
            "enabled": True,
            "status": "sent",
            "service": "persistent_notification.create",
            "notification_id": self.notification_id,
            "analysis_id": analysis_id,
            "mail": mail_delivery,
        }
