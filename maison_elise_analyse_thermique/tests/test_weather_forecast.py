from __future__ import annotations

from datetime import datetime, timedelta
import json
from zoneinfo import ZoneInfo

import httpx

from app.weather_forecast import HomeAssistantWeatherForecastProvider


TZ = ZoneInfo("Europe/Paris")


def _forecast_response(entity_id: str) -> dict:
    return {
        "service_response": {
            entity_id: {
                "forecast": [
                    {
                        "datetime": "2026-08-30T12:00:00+02:00",
                        "condition": "cloudy",
                        "temperature": 21.0,
                        "humidity": 60,
                    },
                    {
                        "datetime": "2026-08-30T13:00:00+02:00",
                        "condition": "partlycloudy",
                        "temperature": 22.0,
                        "dew_point": 13.0,
                        "humidity": 55,
                        "precipitation_probability": 10,
                        "wind_speed": 12.0,
                    },
                    {
                        "datetime": "2026-08-30T14:00:00+02:00",
                        "condition": "sunny",
                        "temperature": 23.0,
                        "humidity": 50,
                        "wind_speed": 14.0,
                    },
                    {
                        "datetime": "2026-08-30T15:00:00+02:00",
                        "condition": "sunny",
                        "temperature": 24.0,
                        "humidity": 48,
                        "wind_speed": 15.0,
                    },
                    {
                        "datetime": "2026-08-30T16:00:00+02:00",
                        "condition": "sunny",
                        "temperature": 24.5,
                        "humidity": 47,
                        "wind_speed": 16.0,
                    },
                    {
                        "datetime": "2026-08-30T17:00:00+02:00",
                        "condition": "sunny",
                        "temperature": 24.0,
                        "humidity": 50,
                    },
                ]
            }
        }
    }


def test_home_assistant_weather_provider_returns_only_h4_and_units() -> None:
    entity_id = "weather.dammarie_les_lys"

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer test-token"
        if request.method == "POST":
            assert request.url.path.endswith("/services/weather/get_forecasts")
            body = json.loads(request.content.decode())
            assert body == {"entity_id": entity_id, "type": "hourly"}
            return httpx.Response(200, json=_forecast_response(entity_id))
        assert request.method == "GET"
        assert request.url.path.endswith(f"/states/{entity_id}")
        return httpx.Response(
            200,
            json={
                "attributes": {
                    "temperature_unit": "°C",
                    "wind_speed_unit": "km/h",
                    "precipitation_unit": "mm",
                }
            },
        )

    reference_end = datetime(2026, 8, 30, 12, 30, tzinfo=TZ)
    provider = HomeAssistantWeatherForecastProvider(
        token="test-token",
        entity_id=entity_id,
        transport=httpx.MockTransport(handler),
        now_fn=lambda _reference: reference_end + timedelta(minutes=5),
    )

    result = provider.get_h4(reference_end)

    assert result["available"] is True
    assert result["entity_id"] == entity_id
    assert len(result["points"]) == 4
    assert result["points"][0]["datetime"] == "2026-08-30T13:00:00+02:00"
    assert result["points"][-1]["datetime"] == "2026-08-30T16:00:00+02:00"
    assert result["points"][0]["dew_point"] == 13.0
    assert result["units"]["temperature"] == "°C"
    assert result["units"]["wind_speed"] == "km/h"
    assert "does_not_prove_indoor_airflow" in result["interpretation_rule"]
    assert "test-token" not in json.dumps(result)


def test_historical_h2_does_not_attach_a_current_forecast_as_if_it_were_historical() -> None:
    def should_not_call(_request: httpx.Request) -> httpx.Response:
        raise AssertionError("historical periods must not call the current forecast")

    reference_end = datetime(2026, 8, 29, 12, 0, tzinfo=TZ)
    provider = HomeAssistantWeatherForecastProvider(
        token="test-token",
        entity_id="weather.dammarie_les_lys",
        transport=httpx.MockTransport(should_not_call),
        now_fn=lambda _reference: datetime(2026, 8, 30, 12, 0, tzinfo=TZ),
    )

    result = provider.get_h4(reference_end)

    assert result["available"] is False
    assert result["reason"] == "historical_or_future_period_current_forecast_not_representative"


def test_home_assistant_forecast_error_is_non_blocking_and_sanitized() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"message": "boom"})

    reference_end = datetime(2026, 8, 30, 12, 0, tzinfo=TZ)
    provider = HomeAssistantWeatherForecastProvider(
        token="secret-token",
        entity_id="weather.dammarie_les_lys",
        transport=httpx.MockTransport(handler),
        now_fn=lambda _reference: reference_end,
    )

    result = provider.get_h4(reference_end)

    assert result["available"] is False
    assert result["reason"] == "home_assistant_forecast_error"
    assert result["error_type"] == "HTTPStatusError"
    assert "secret-token" not in json.dumps(result)
