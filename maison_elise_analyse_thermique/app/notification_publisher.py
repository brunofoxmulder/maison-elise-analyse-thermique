from __future__ import annotations

from threading import Lock

import httpx

from .notification_report import build_notification_report, notification_title


DEFAULT_NOTIFICATION_ID = "maison_elise_analyse_thermique"


def _result_key(result: dict) -> str:
    comparison = result.get("comparison") or {}
    comparison_mode = comparison.get("mode")
    expertise = result.get("expertise_h2")
    if isinstance(expertise, dict):
        observed_end = (expertise.get("data_window") or {}).get("observed_end")
        if observed_end:
            return f"h2:{observed_end}:{comparison_mode}"
    period = result.get("period") or {}
    return "period:{start}:{end}:{compare}".format(
        start=period.get("start"),
        end=period.get("end"),
        compare=comparison_mode,
    )


class UnavailableNotificationPublisher:
    def __init__(self, reason: str = "home_assistant_api_unavailable") -> None:
        self.reason = reason

    def publish(self, result: dict) -> dict:
        return {
            "enabled": False,
            "status": "disabled",
            "reason": self.reason,
        }


class HomeAssistantNotificationPublisher:
    """Publie le rapport détaillé dans les notifications persistantes de HA.

    Cette sortie ne commande aucun équipement. Elle appelle uniquement le
    service ``persistent_notification.create`` de Home Assistant. Un identifiant
    stable évite d'accumuler une pile de rapports horaires : la notification
    Maison Élise courante est mise à jour à chaque nouvelle analyse.
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
        self._last_key: str | None = None
        self._lock = Lock()

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

    def publish(self, result: dict) -> dict:
        key = _result_key(result)
        with self._lock:
            if self._last_key == key:
                return {
                    "enabled": True,
                    "status": "duplicate_skipped",
                    "service": "persistent_notification.create",
                    "notification_id": self.notification_id,
                    "key": key,
                }

        payload = {
            "title": notification_title(result),
            "message": build_notification_report(result),
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
                "error_type": type(exc).__name__,
            }

        with self._lock:
            self._last_key = key
        return {
            "enabled": True,
            "status": "sent",
            "service": "persistent_notification.create",
            "notification_id": self.notification_id,
            "key": key,
        }
