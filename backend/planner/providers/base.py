"""Provider interfaces. The planner only depends on these, never on a vendor SDK."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol

from ..domain.geometry import LatLon
from ..domain.weather import WeatherSeries


class ProviderError(Exception):
    """An upstream API failed. `message` is safe to show to the user."""

    def __init__(self, message: str, status_code: int = 502):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class NoRouteFound(ProviderError):
    def __init__(self, message: str = "No truck route was found between these locations."):
        super().__init__(message, status_code=422)


@dataclass(frozen=True)
class Place:
    label: str
    lat: float
    lon: float

    @property
    def latlon(self) -> LatLon:
        return (self.lat, self.lon)


@dataclass
class RouteOption:
    points: list[LatLon]
    length_m: float
    travel_time_s: float
    traffic_delay_s: float = 0.0
    # Cumulative progress knots from the provider: (point index, driving seconds).
    progress: list[tuple[int, float]] = field(default_factory=list)
    road_numbers: list[str] = field(default_factory=list)
    strategy: str = "fastest"


class RoutingProvider(Protocol):
    def routes(self, origin: Place, destination: Place, depart_at: datetime, load_lbs: float) -> list[RouteOption]: ...


class Geocoder(Protocol):
    def search(self, query: str) -> list[Place]: ...


class WeatherProvider(Protocol):
    name: str

    def series(self, locations: list[LatLon], start: datetime, end: datetime) -> list[WeatherSeries]:
        """Hourly series covering [start, end] (UTC hours), one per location, in order."""
        ...
