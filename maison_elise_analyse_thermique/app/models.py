from dataclasses import dataclass
from datetime import datetime
from typing import Optional

@dataclass(frozen=True)
class ThermalSample:
    ts: datetime
    temp_indoor: Optional[float]
    humidity_indoor: Optional[float]
    temp_outdoor_ref: Optional[float]
    humidity_outdoor: Optional[float]
    setpoint: Optional[float]
    hvac_mode: Optional[str]
    hvac_action: Optional[str]
    compressor_frequency: Optional[float]
    compressor_energy_day: Optional[float]
    cool_energy_last_hour: Optional[float]
    heat_energy_last_hour: Optional[float]
    lux: Optional[float]
    sun_elevation: Optional[float]
    sun_azimuth: Optional[float]
    shutter_salon: Optional[float]
    shutter_terrasse: Optional[float]
    window_open: Optional[bool]
    door_window_open: Optional[bool]
    # Sonde du groupe extérieur Daikin : contexte de microclimat terrasse
    # uniquement. Elle ne remplace jamais la température extérieure fiable.
    temp_outdoor_daikin: Optional[float] = None
    # Historique du signal de vie : True = réveillé, False = dort.
    # Ce champ doit provenir de la ligne historique analysée, jamais de l'état HA actuel.
    awake: Optional[bool] = None
