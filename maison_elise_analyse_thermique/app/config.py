from dataclasses import dataclass

@dataclass(frozen=True)
class AnalysisConfig:
    # Deux niveaux distincts après benchmark multi-jours :
    # - >2 °C / ~5 min : marche suspecte, conservée mais signalée ;
    # - >4 °C / ~5 min : valeur rejetée des calculs principaux.
    # Une marche suspecte suffit à interdire une conclusion forte sur
    # l'efficacité du Daikin pour la période concernée.
    outdoor_flag_jump_c_per_5min: float = 2.0
    outdoor_reject_jump_c_per_5min: float = 4.0
    minimum_coverage_for_strong_claim: float = 0.90
    shutter_closed_max: float = 5.0
    shutter_open_min: float = 95.0

    # Fenêtre géométrique du salon reprise de l'automatisation de production
    # "Gestion volet salon avec soleil et saison" : azimut 54° à 165° et
    # élévation positive. Cette géométrie reste indépendante de la luminosité.
    sun_azimuth_in: float = 54.0
    sun_azimuth_out: float = 165.0
    sun_elevation_min: float = 0.0

    # Borne haute du modèle d'exposition EFFECTIVE actuel. Elle ne signifie
    # pas que le soleil sort géométriquement de la fenêtre à 65° : au-dessus,
    # le moteur refuse seulement de qualifier une exposition directe/effective
    # tant que la géométrie réelle n'est pas validée terrain.
    sun_elevation_effective_model_max: float = 65.0

    # Seuil de contexte lumineux simple. Il ne convertit pas les lux en énergie
    # solaire : il permet seulement de signaler un ciel très lumineux, y compris
    # lorsque le soleil est hors de la fenêtre géométrique.
    bright_sky_lux_min: float = 15000.0

    # Seuil utilisé par la correction de position de l'automatisation.
    sun_effective_lux_min: float = 15000.0

    # Seuils lux de la logique de production par paliers d'élévation.
    sun_lux_stage_15: float = 8000.0
    sun_lux_stage_35: float = 25000.0
    sun_lux_stage_45: float = 35000.0
    sun_lux_stage_55: float = 45000.0
    sun_lux_stage_65: float = 50000.0
