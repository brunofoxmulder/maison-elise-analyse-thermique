from app.assist_brief import build_assist_brief_facts


def _result():
    return {
        "analysis": {
            "hvac_action_minutes": {"cooling": 115.0},
        },
        "expertise_h2": {
            "primary_period": {
                "start": "2026-08-30T18:30:00+02:00",
                "end": "2026-08-30T19:30:00+02:00",
            },
            "reference_period": {
                "start": "2026-08-30T17:30:00+02:00",
                "end": "2026-08-30T18:30:00+02:00",
            },
            "last_hour": {
                "analysis": {
                    "temperature_indoor": {"mean": 21.3},
                    "temperature_outdoor_reference": {"mean": 24.1},
                    "delta_outdoor_minus_indoor": {"mean": 2.8},
                    "humidity_indoor": {"mean": 54.0},
                    "humidity_outdoor": {"mean": 53.0},
                    "hvac_action_minutes": {"cooling": 55.0},
                    "compressor_frequency": {"mean": 16.0},
                    "openings": {
                        "window_open_minutes": 0.0,
                        "door_window_open_minutes": 0.0,
                    },
                    "shutters": {
                        "salon": {"mean": 100.0},
                        "terrasse": {"mean": 100.0},
                    },
                    "solar_exposure": {
                        "effective_minutes": 0.0,
                        "bright_sky_minutes": 0.0,
                    },
                    "cross_contexts": {
                        "effective_sun_with_salon_shutter_open_minutes": 0.0,
                    },
                },
                "temperature_trend": {"delta_c": 0.0},
                "setpoint_tracking": {
                    "latest_setpoint_c": 21.0,
                    "indoor_minus_setpoint_c": {"mean": 0.3},
                },
                "air_properties": {
                    "indoor_absolute_humidity_g_m3": {"mean": 10.1},
                    "outdoor_absolute_humidity_g_m3": {"mean": 11.2},
                },
                "hourly_energy_observation": {
                    "cool_energy_last_hour_kwh": {"value": 0.3},
                    "heat_energy_last_hour_kwh": {"value": 0.0},
                },
            },
            "comparison": {
                "temperature_evolution_classification": {
                    "id": "stable_both_hours",
                    "label_fr": "stabilité sur les deux heures",
                },
                "indoor_temperature_mean_delta_c": 0.0,
            },
            "forecast_h4": {
                "available": True,
                "points": [
                    {
                        "datetime": "2026-08-30T20:00:00+02:00",
                        "temperature": 18.0,
                        "humidity": 80.0,
                    }
                ],
            },
        },
    }


def test_brief_uses_last_hour_not_two_hour_aggregate() -> None:
    brief = build_assist_brief_facts(_result())
    assert brief is not None
    assert brief["daikin"]["cooling_minutes_last_hour"] == 55.0
    assert brief["daikin"]["cooling_minutes_last_hour"] != 115.0
    assert "never_use_two_hour_top_level_durations" in brief["scope"]["rule"]


def test_brief_exposes_shutter_state_and_solar_context_without_inversion() -> None:
    brief = build_assist_brief_facts(_result())
    assert brief["shutters"]["salon"]["mean_open_pct"] == 100.0
    assert brief["shutters"]["salon"]["state"] == "open"
    assert brief["shutters"]["terrasse"]["state"] == "open"
    assert brief["solar"]["effective_sun_minutes_last_hour"] == 0.0
    assert "do_not_recommend_closing_shutters_solely_because_it_is_daytime" in brief["solar"]["rule"]


def test_brief_causal_and_humidity_guardrails_are_explicit() -> None:
    brief = build_assist_brief_facts(_result())
    assert "never_say_it_explains_continuous_cooling_by_itself" in brief["outdoor"]["rule"]
    assert "relative_humidity_alone" in brief["humidity"]["rule"]
    assert brief["forecast"]["points"][0]["temperature"] == 18.0
    assert "never_extend_beyond_the_last_point" in brief["forecast"]["rule"]
