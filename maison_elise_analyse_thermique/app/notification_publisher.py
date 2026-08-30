from __future__ import annotations

from threading import Lock

import httpx

from .notification_report import build_notification_report, notification_title


def _result_key(result: dict) -> str:
    expertise = result.get("expertise_h2")
    if isinstance(expertise, dict):
        observed_end = (expertise.get("data_window") or {}).get("observed_end")
        if observed_end:
            return f"h2:{observed_end}"
    period = result.get("period") or {}
    comparison = result.get("comparison") or {}
    return "period:{start}:{end}:{compare}".format(
        start=period.get("start"),
        end=period.get("end"),
        compare=comparison.get("mode"),
    )


class UnavailableNotificationPublisher:
    def __init__(self, reason: str = "notification_service_not_configured") -> None:
        self.reason = reason

    def publish(self, result: dict) -> dict:
        return {
            "enabled": False,
            "status": "disabled",
            "reason": self.reason,
        }


class HomeAssistantNotificationPublisher:
    """Publie uniquement une notification ; aucun équipement n'est commandé."""

    def __init__(
        self,
        token: str,
        service_target: str,
        *,
        base_url: str = "http://supervisor/core/api",
        timeout_seconds: float = 5.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if not token:
            raise ValueError("Home Assistant token is required")
        if not isinstance(service_target, str) or not service_target.startswith("notify."):
            raise ValueError("notification service must use notify.<service>")
        domain, service = service_target.split(".", 1)
        if not service:
            raise ValueError("notification service must use notify.<service>")
        self.token = token
        self.service_target = service_target
        self.domain = domain
        self.service = service
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
                    "service": self.service_target,
                    "key": key,
                }

        payload = {
            "title": notification_title(result),
            "message": build_notification_report(result),
        }
        try:
            with httpx.Client(timeout=self.timeout_seconds, transport=self.transport) as client:
                response = client.post(
                    f"{self.base_url}/services/{self.domain}/{self.service}",
                    headers=self._headers(),
                    json=payload,
                )
                response.raise_for_status()
        except Exception as exc:
            return {
                "enabled": True,
                "status": "error",
                "service": self.service_target,
                "error_type": type(exc).__name__,
            }

        with self._lock:
            self._last_key = key
        return {
            "enabled": True,
            "status": "sent",
            "service": self.service_target,
            "key": key,
        }
