from __future__ import annotations

import json
import httpx

from app.expert_report import build_expert_report, render_expert_report
from app.notification_publisher import HomeAssistantNotificationPublisher


def _expert_report():
    return build_expert_report(
        analysis_id="thermal-test",
        status="NORMAL",
        short_response=(
            "Le salon reste stable à 21,3 °C près de la consigne. "
            "Aucune action particulière n'est nécessaire pour le moment."
        ),
        situation=(
            "La dernière heure est stable à 21,3 °C pour une consigne de 21,0 °C, "
            "avec 54 % d'humidité intérieure."
        ),
        evolution=(
            "La température intérieure reste stable par rapport à l'heure précédente, "
            "tandis que l'extérieur fiable baisse progressivement."
        ),
        energy="Le Daikin a consommé 0,20 kWh sur la dernière heure à faible fréquence compresseur.",
        explanations=(
            "Fait : la température intérieure est stable. Hypothèse : la modulation du Daikin "
            "est compatible avec le maintien de la consigne ; ce n'est pas une causalité prouvée."
        ),
        shutters_advice="Maintenir l'état actuel ; aucun apport solaire direct pertinent n'est observé.",
        ventilation_advice=(
            "Pas d'ouverture immédiate recommandée ; réévaluer lorsque température et humidité absolue "
            "extérieures deviennent réellement favorables."
        ),
        daikin_advice="Conserver le fonctionnement actuel tant que le confort reste stable.",
        outlook="L'horizon H+4 prévoit un rafraîchissement progressif de l'extérieur.",
        vigilance="Aucun point de vigilance particulier pour le moment.",
        conclusion="Le confort est maîtrisé et stable ; aucune action immédiate n'est nécessaire.",
        source_period={
            "primary_period": {
                "start": "2026-08-30T19:00:00+02:00",
                "end": "2026-08-30T20:00:00+02:00",
            }
        },
    )


def test_expert_report_matches_hourly_pyscript_structure() -> None:
    text = render_expert_report(_expert_report())
    assert "## Situation" in text
    assert "## Évolution par rapport à l’heure précédente" in text
    assert "## ⚡ Énergie Daikin" in text
    assert "## Explications prudentes" in text
    assert "## Conseil pour les 2 à 4 prochaines heures" in text
    assert "**Volets :**" in text
    assert "**Aération :**" in text
    assert "**Daikin :**" in text
    assert "**À venir :**" in text
    assert "## Points de vigilance" in text
    assert "## Conclusion" in text
    assert "**NORMAL.**" in text


def test_home_assistant_persistent_notification_publishes_expert_report_once() -> None:
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=[])

    publisher = HomeAssistantNotificationPublisher(
        token="secret-token",
        transport=httpx.MockTransport(handler),
    )
    report = _expert_report()

    first = publisher.publish(report)
    second = publisher.publish(report)

    assert first["status"] == "sent"
    assert first["service"] == "persistent_notification.create"
    assert first["analysis_id"] == "thermal-test"
    assert second["status"] == "duplicate_skipped"
    assert len(requests) == 1
    request = requests[0]
    assert request.url.path.endswith("/services/persistent_notification/create")
    assert request.headers["authorization"] == "Bearer secret-token"
    payload = json.loads(request.content)
    assert payload["notification_id"] == "maison_elise_analyse_thermique"
    assert payload["title"] == "Analyse thermique — heure · NORMAL"
    assert "## Situation" in payload["message"]
    assert "Fait :" in payload["message"]
    assert "Hypothèse :" in payload["message"]
    assert "**NORMAL.**" in payload["message"]
