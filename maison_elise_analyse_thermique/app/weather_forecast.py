from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import httpx


FORECAST_HORIZON_HOURS = 4
MAX_FORECAST_POINTS = 5


def _unavailable(reason: str, *, entity_id: str | None = None, error_type: str | None = None) -> dict:
    out = {
        "available": False,
        "reason": reason,
        "source": "home_assistant_weather_hourly_forecast",
        "horizon_hours": FORECAST_HORIZON_HOURS,
        "points": [],
        "interpretation_rule": (
            "forecast_is_prospective_context_not_a_certainty; "
            "never_invent_missing_forecast_values"
        ),
    }
    if entity_id:
        out["entity_id"] = entity_id
    if error_type:
        out["error_type"] = error_type
    return out


def _parse_datetime(value: Any, fallback_tz) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=fallback_tz)
    return dt


def _normalize_point(raw: dict) -> dict:
    # Keep only weather fields useful for the thermal expert. The provider may
    # omit any of them; absence remains explicit rather than being guessed.
    keys = (
        "datetime",
        "condition",
        "temperature",
        "apparent_temperature",
        "dew_point",
        "humidity",
        "precipitation",
        "precipitation_probability",
        "wind_speed",
        "wind_gust_speed",
        "wind_bearing",
        "cloud_coverage",
    )
    return {key: raw.get(key) for key in keys if key in raw}


class UnavailableWeatherForecastProvider:
    """Null object used outside HAOS or when Core API access is unavailable."""

    def __init__(self, reason: str = "provider_not_configured") -> None:
        self.reason = reason

    def get_h4(self, reference_end: datetime) -> dict:
        return _unavailable(self.reason)


class HomeAssistantWeatherForecastProvider:
    """Read-only H+4 weather context from Home Assistant's weather service.

    The only service invoked is ``weather.get_forecasts``. The Supervisor token
    is never returned in the analysis payload or logs by this class.
    """

    def __init__(
        self,
        token: str,
        entity_id: str,
        *,
        base_url: str = "http://supervisor/core/api",
        timeout_seconds: float = 5.0,
        max_reference_age_minutes: float = 45.0,
        future_tolerance_minutes: float = 15.0,
        transport: httpx.BaseTransport | None = None,
        now_fn=None,
    ) -> None:
        if not token:
            raise ValueError("Home Assistant token is required")
        if not entity_id or not entity_id.startswith("weather."):
            raise ValueError("weather entity_id is required")
        self.token = token
        self.entity_id = entity_id
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = float(timeout_seconds)
        self.max_reference_age_minutes = float(max_reference_age_minutes)
        self.future_tolerance_minutes = float(future_tolerance_minutes)
        self.transport = transport
        self.now_fn = now_fn

    def _now(self, reference_end: datetime) -> datetime:
        if self.now_fn is not None:
            return self.now_fn(reference_end)
        return datetime.now(reference_end.tzinfo)

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

    def _forecast_payload(self, client: httpx.Client) -> dict:
        response = client.post(
            f"{self.base_url}/services/weather/get_forecasts?return_response",
            headers=self._headers(),
            json={"entity_id": self.entity_id, "type": "hourly"},
        )
        response.raise_for_status()
        return response.json()

    def _units(self, client: httpx.Client) -> dict:
        try:
            response = client.get(
                f"{self.base_url}/states/{self.entity_id}",
                headers=self._headers(),
            )
            response.raise_for_status()
            attrs = (response.json() or {}).get("attributes", {})
        except Exception:
            return {}
        mapping = {
            "temperature": attrs.get("temperature_unit"),
            "apparent_temperature": attrs.get("temperature_unit"),
            "dew_point": attrs.get("temperature_unit"),
            "precipitation": attrs.get("precipitation_unit"),
            "wind_speed": attrs.get("wind_speed_unit"),
            "wind_gust_speed": attrs.get("wind_speed_unit"),
        }
        return {key: value for key, value in mapping.items() if value is not None}

    def _extract_forecast(self, payload: dict) -> list[dict]:
        service_response = payload.get("service_response", payload)
        entity_payload = service_response.get(self.entity_id)
        if entity_payload is None and isinstance(service_response, dict) and len(service_response) == 1:
            entity_payload = next(iter(service_response.values()))
        if not isinstance(entity_payload, dict):
            return []
        forecast = entity_payload.get("forecast", [])
        return forecast if isinstance(forecast, list) else []

    def get_h4(self, reference_end: datetime) -> dict:
        if reference_end.tzinfo is None or reference_end.utcoffset() is None:
            return _unavailable("reference_end_must_be_timezone_aware", entity_id=self.entity_id)

        now = self._now(reference_end)
        age_minutes = (now - reference_end).total_seconds() / 60.0
        if age_minutes > self.max_reference_age_minutes or age_minutes < -self.future_tolerance_minutes:
            return _unavailable(
                "historical_or_future_period_current_forecast_not_representative",
                entity_id=self.entity_id,
            )

        try:
            with httpx.Client(timeout=self.timeout_seconds, transport=self.transport) as client:
                payload = self._forecast_payload(client)
                units = self._units(client)
        except Exception as exc:
            return _unavailable(
                "home_assistant_forecast_error",
                entity_id=self.entity_id,
                error_type=type(exc).__name__,
            )

        horizon_end = reference_end + timedelta(hours=FORECAST_HORIZON_HOURS)
        selected = []
        for raw in self._extract_forecast(payload):
            if not isinstance(raw, dict):
                continue
            dt = _parse_datetime(raw.get("datetime"), reference_end.tzinfo)
            if dt is None:
                continue
            comparable_dt = dt.astimezone(reference_end.tzinfo)
            if comparable_dt < reference_end or comparable_dt > horizon_end:
                continue
            normalized = _normalize_point(raw)
            normalized["datetime"] = dt.isoformat()
            selected.append((dt, normalized))

        selected.sort(key=lambda item: item[0])
        points = [item[1] for item in selected[:MAX_FORECAST_POINTS]]
        if not points:
            return _unavailable("no_hourly_forecast_points_in_h4", entity_id=self.entity_id)

        return {
            "available": True,
            "reason": None,
            "source": "home_assistant_weather_hourly_forecast",
            "entity_id": self.entity_id,
            "horizon_hours": FORECAST_HORIZON_HOURS,
            "reference_end": reference_end.isoformat(),
            "points": points,
            "units": units,
            "interpretation_rule": (
                "forecast_is_prospective_context_not_a_certainty; "
                "outdoor_wind_can_inform_ventilation_potential_but_does_not_prove_indoor_airflow; "
                "never_invent_missing_forecast_values"
            ),
        }
