from datetime import datetime, timedelta

import pytest

from app.day_profile import build_setpoint_profiles
from app.expert_report import build_expert_report, notification_title, render_expert_report
from app.models import ThermalSample


def _sample(ts, *, setpoint, hvac_mode, temp_indoor):
    return ThermalSample(
        ts=ts,
        temp_indoor=temp_indoor,
        humidity_indoor=50.0,
        temp_outdoor_ref=25.0,
        humidity_outdoor=50.0,
        setpoint=setpoint,
        hvac_mode=hvac_mode,
        hvac_action="cooling" if hvac_mode == "cool" else "heating",
        compressor_frequency=16.0,
        compressor_energy_day=1.0,
        cool_energy_last_hour=0.2,
        heat_energy_last_hour=0.0,
        lux=0.0,
        sun_elevation=0.0,
        sun_azimuth=0.0,
        shutter_salon=100.0,
        shutter_terrasse=100.0,
        window_open=False,
        door_window_open=False,
    )


@pytest.mark.parametrize(
    ("mode", "first_setpoint", "second_setpoint", "first_indoor", "second_indoor"),
    [
        ("cool", 22.0, 20.0, 22.2, 20.3),
        ("heat", 18.0, 20.0, 18.1, 19.8),
    ],
)
def test_day_profile_highlights_two_recorded_requested_temperatures(
    mode, first_setpoint, second_setpoint, first_indoor, second_indoor
):
    start = datetime.fromisoformat("2026-08-20T00:00:00+02:00")
    samples = []
    for index in range(25):
        first_half = index <= 12
        samples.append(
            _sample(
                start + timedelta(minutes=5 * index),
                setpoint=first_setpoint if first_half else second_setpoint,
                hvac_mode=mode,
                temp_indoor=first_indoor if first_half else second_indoor,
            )
        )

    profile = build_setpoint_profiles(samples)
    assert profile["dominant_active_hvac_mode"] == mode
    mode_profile = profile["modes"][mode]
    assert set(mode_profile["dominant_two_requested_temperatures_c"]) == {
        first_setpoint,
        second_setpoint,
    }
    assert set(mode_profile["distinct_requested_temperatures_c"]) == {
        first_setpoint,
        second_setpoint,
    }
    assert all(regime["segments"] for regime in mode_profile["regimes"])
    assert all(regime["mean_abs_tracking_error_c"] is not None for regime in mode_profile["regimes"])
    assert profile["tracking_band_semantics"] == "descriptive_tracking_only_not_a_comfort_threshold"
    assert "recorded_Consigne" in profile["setpoint_source_rule"]


def test_day_expert_report_has_day_specific_notification_sections():
    report = build_expert_report(
        analysis_id="thermal-day-test",
        profile="day",
        status="NORMAL",
        short_response="Journée stable, deux consignes suivies correctement.",
        situation="Le salon est resté stable sur la journée.",
        setpoints="Deux consignes enregistrées : 20 °C puis 22 °C, analysées séparément.",
        evolution="Pas de dérive notable au fil de la journée.",
        energy="Consommation cohérente avec le fonctionnement observé.",
        explanations="Faits et hypothèses restent distingués.",
        shutters_advice="Pas de conclusion causale à partir de la position seule.",
        ventilation_advice="L'humidité relative seule ne suffit pas à conclure.",
        daikin_advice="Fonctionnement cohérent sur les séquences observées.",
        outlook="Journée historique : aucune projection future n'est ajoutée.",
        vigilance="Aucun point particulier.",
        conclusion="Journée thermiquement maîtrisée.",
    )

    rendered = render_expert_report(report)
    assert "## 🌡️ Consignes et suivi" in rendered
    assert "## Évolution de la journée" in rendered
    assert "## Bilan et recommandations" in rendered
    assert notification_title(report) == "Analyse thermique — jour · NORMAL"


def test_day_report_requires_setpoint_section():
    with pytest.raises(ValueError, match="setpoints is required"):
        build_expert_report(
            analysis_id="thermal-day-test",
            profile="day",
            status="NORMAL",
            short_response="Résumé.",
            situation="Situation.",
            evolution="Évolution.",
            energy="Énergie.",
            explanations="Explications.",
            shutters_advice="Volets.",
            ventilation_advice="Aération.",
            daikin_advice="Daikin.",
            outlook="Suite.",
            vigilance="Vigilance.",
            conclusion="Conclusion.",
        )
