from __future__ import annotations

import json
import httpx

from app.notification_publisher import HomeAssistantNotificationPublisher
from app.notification_report import build_notification_report


def _h2_result():
    return {
        "period": {
            "start": "2026-08-30T16:50:00+02:00",
            "end": "2026-08-30T18:50:00+02:00",
        },
        "expertise_h2": {
            "primary_period": {
                "start": "2026-08-30T17:50:00+02:00",
                "end": "2026-08-30T18:50:00+02:00",
            },
            "last_hour": {
                "analysis": {
                    "temperature_indoor": {"mean": 21.3, "min": 21.3, "max": 21.3},
                    "temperature_outdoor_reference": {"mean": 24.1},
                    "humidity_indoor": {"mean": 54.0},
                    "hvac_action_minutes": {"cooling": 60.0},
                    "compressor_frequency": {"mean": 16.0},
                    "openings": {
                        "window_open_minutes": 0.0,
                        "door_window_open_minutes": 0.0,
                    },
                    "shutters": {
                        "salon": {"mean": 100.0},
                        "terrasse": {"mean": 100.0},
                    },
                },
                "temperature_trend": {"delta_c": 0.0},
                "setpoint_tracking": {"latest_setpoint_c": 21.0},
                "air_properties": {
                    "indoor_absolute_humidity_g_m3": {"mean": 10.1},
                    "outdoor_absolute_humidity_g_m3": {"mean": 11.2},
                },
                "hourly_energy_observation": {
                    "cool_energy_last_hour_kwh": {"value": 0.3}
                },
            },
            "comparison": {
                "temperature_evolution_classification": {
                    "id": "stable_both_hours",
                    "label_fr": "stabilité sur les deux heures",
                },
                "indoor_temperature_mean_delta_c": 0.1,
            },
            "data_window": {
                "observed_end": "2026-08-30T18:50:00+02:00",
                "last_hour_samples": 13,
                "requested_end_to_observed_end_lag_minutes": 1.0,
            },
            "forecast_h4": {
                "available": True,
                "points": [
                    {
                        "datetime": "2026-08-30T19:00:00+02:00",
                        "temperature": 23.0,
                        "condition": "sunny",
                    },
                    {
                        "datetime": "2026-08-30T22:00:00+02:00",
                        "temperature": 20.0,
                        "condition": "clear-night",
                    },
                ],
            },
        },
    }


def test_detailed_notification_states_shutter_semantics_and_h4_only() -> None:
    text = build_notification_report(_h2_result())
    assert "salon 100 % (ouvert)" in text
    assert "terrasse 100 % (ouvert)" in text
    assert "0 % = fermé, 100 % = ouvert" in text
    assert "À venir H+4" in text
    assert "2026-08-30T22:00:00+02:00" in text
    assert "demain" not in text.lower()


def test_home_assistant_persistent_notification_updates_one_ha_notification() -> None:
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=[])

    publisher = HomeAssistantNotificationPublisher(
        token="secret-token",
        transport=httpx.MockTransport(handler),
    )
    result = _h2_result()

    first = publisher.publish(result)
    second = publisher.publish(result)

    assert first["status"] == "sent"
    assert first["service"] == "persistent_notification.create"
    assert second["status"] == "duplicate_skipped"
    assert len(requests) == 1
    request = requests[0]
    assert request.url.path.endswith("/services/persistent_notification/create")
    assert request.headers["authorization"] == "Bearer secret-token"
    payload = json.loads(request.content)
    assert payload["notification_id"] == "maison_elise_analyse_thermique"
    assert "Analyse thermique" in payload["title"]
    assert "100 % (ouvert)" in payload["message"]
