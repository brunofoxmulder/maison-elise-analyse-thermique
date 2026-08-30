from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app.models import ThermalSample
from app.service import ThermalAnalysisService


TZ = ZoneInfo("Europe/Paris")


class FakeSource:
    def __init__(self, samples):
        self.samples = samples

    def load(self, start, end):
        return [sample for sample in self.samples if start <= sample.ts < end]


class FakeForecastProvider:
    def __init__(self):
        self.calls = []

    def get_h4(self, reference_end):
        self.calls.append(reference_end)
        return {
            "available": True,
            "source": "test_weather",
            "horizon_hours": 4,
            "points": [
                {
                    "datetime": (reference_end + timedelta(hours=1)).isoformat(),
                    "temperature": 22.0,
                    "humidity": 55,
                }
            ],
        }


def _sample(ts):
    return ThermalSample(
        ts=ts,
        temp_indoor=20.5,
        humidity_indoor=55.0,
        temp_outdoor_ref=18.0,
        humidity_outdoor=70.0,
        setpoint=21.0,
        hvac_mode="cool",
        hvac_action="cooling",
        compressor_frequency=20.0,
        compressor_energy_day=4.0 + ts.minute / 1000.0,
        cool_energy_last_hour=0.15,
        heat_energy_last_hour=0.0,
        lux=10000.0,
        sun_elevation=20.0,
        sun_azimuth=100.0,
        shutter_salon=50.0,
        shutter_terrasse=50.0,
        window_open=False,
        door_window_open=False,
        temp_outdoor_daikin=22.0,
    )


def test_h2_expertise_attaches_forecast_and_prompt_contract() -> None:
    start = datetime(2026, 8, 30, 10, 0, tzinfo=TZ)
    end = start + timedelta(hours=2)
    samples = [_sample(start + timedelta(minutes=5 * index)) for index in range(24)]
    forecast = FakeForecastProvider()

    result = ThermalAnalysisService(
        FakeSource(samples),
        forecast_provider=forecast,
    ).analyse(start, end)

    h2 = result["expertise_h2"]
    assert h2["forecast_h4"]["available"] is True
    assert h2["forecast_h4"]["source"] == "test_weather"
    assert forecast.calls == [end]

    contract = h2["analysis_contract"]
    assert contract["prompt_version"] == "h2-expert-v1"
    assert "missing_forecast_must_be_reported_as_uncertainty" in contract["forecast_rule"]
    assert "never_proves_indoor_airflow" in contract["wind_rule"]
    assert contract["response_contract"]["status"] == ["NORMAL", "VIGILANCE", "ALERTE"]
    assert contract["response_contract"]["advice_labels"] == ["Volets", "Aération", "Daikin"]


def test_h2_without_weather_provider_remains_valid_and_explicitly_uncertain() -> None:
    start = datetime(2026, 8, 30, 10, 0, tzinfo=TZ)
    end = start + timedelta(hours=2)
    samples = [_sample(start + timedelta(minutes=5 * index)) for index in range(24)]

    result = ThermalAnalysisService(FakeSource(samples)).analyse(start, end)

    forecast = result["expertise_h2"]["forecast_h4"]
    assert forecast["available"] is False
    assert forecast["reason"] == "provider_not_configured"
    assert result["expertise_h2"]["last_hour"]["analysis"]["samples"] > 0
