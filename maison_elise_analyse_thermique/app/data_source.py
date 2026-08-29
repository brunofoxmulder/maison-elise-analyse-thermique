from abc import ABC, abstractmethod
from datetime import datetime
from .models import ThermalSample


class DataSource(ABC):
    @abstractmethod
    def load(self, start: datetime, end: datetime) -> list[ThermalSample]:
        """Charge les échantillons de la période demi-ouverte [start, end)."""
        raise NotImplementedError


class InMemoryDataSource(DataSource):
    def __init__(self, samples):
        self.samples = list(samples)

    def load(self, start, end):
        return [s for s in self.samples if start <= s.ts < end]
