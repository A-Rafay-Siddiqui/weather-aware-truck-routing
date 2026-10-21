"""Deterministic simulated weather: a moving storm placed on the trip.

Live weather is calm most days, so every checkpoint comes out Low and the ranking logic never
gets exercised. This provider puts a strong storm cell on the fastest route at the time the
truck would reach it. That shows rerouting, load rules and the heatmap without waiting for
real bad weather, and it makes integration tests repeatable.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone

from ..domain.geometry import LatLon, haversine_miles
from ..domain.weather import WeatherSeries

HOUR = 3600


@dataclass(frozen=True)
class Storm:
    lat: float
    lon: float
    peak_time: float  # unix seconds when the storm is strongest at (lat, lon)
    radius_miles: float = 60.0
    duration_hours: float = 8.0  # e-folding half-width of the intensity curve in time
    heading_deg: float = 60.0  # direction the cell moves toward (0 = north)
    speed_mph: float = 20.0
    peak_wind_mph: float = 62.0
    peak_rain_in_hr: float = 0.9
    peak_snow_in_hr: float = 0.0

    def center_at(self, t: float) -> LatLon:
        hours = (t - self.peak_time) / HOUR
        miles = self.speed_mph * hours
        dlat = miles * math.cos(math.radians(self.heading_deg)) / 69.0
        dlon = miles * math.sin(math.radians(self.heading_deg)) / (69.0 * math.cos(math.radians(self.lat)))
        return (self.lat + dlat, self.lon + dlon)

    def intensity(self, loc: LatLon, t: float) -> float:
        """0–1: Gaussian falloff in space around the moving center and in time around the peak."""
        d = haversine_miles(loc, self.center_at(t))
        spatial = math.exp(-((d / self.radius_miles) ** 2))
        temporal = math.exp(-(((t - self.peak_time) / (self.duration_hours * HOUR)) ** 2))
        return spatial * temporal


@dataclass(frozen=True)
class SyntheticWeather:
    storms: tuple[Storm, ...]
    name: str = "simulated"
    base_wind_mph: float = 8.0

    def series(self, locations: list[LatLon], start: datetime, end: datetime) -> list[WeatherSeries]:
        t0 = int(start.astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0).timestamp())
        t1 = int(end.timestamp())
        times = list(range(t0, t1 + HOUR, HOUR))
        return [self._at_location(loc, times) for loc in locations]

    def _at_location(self, loc: LatLon, times: list[int]) -> WeatherSeries:
        wind, gust, rain, snow = [], [], [], []
        for t in times:
            w, r, s = self.base_wind_mph, 0.0, 0.0
            for storm in self.storms:
                k = storm.intensity(loc, t)
                w += (storm.peak_wind_mph - self.base_wind_mph) * k
                r += storm.peak_rain_in_hr * k
                s += storm.peak_snow_in_hr * k
            wind.append(round(w, 1))
            gust.append(round(w * 1.35, 1))
            rain.append(round(r, 3))
            snow.append(round(s, 3))
        return WeatherSeries(loc[0], loc[1], times, wind, gust, rain, snow, [None] * len(times))

    def to_dict(self) -> dict:
        return {"storms": [asdict(s) for s in self.storms]}

    @classmethod
    def from_dict(cls, data: dict) -> SyntheticWeather:
        return cls(storms=tuple(Storm(**s) for s in data.get("storms", [])))


def storms_for_trip(anchor: LatLon, anchor_eta: datetime, secondary: LatLon | None, secondary_eta: datetime | None):
    """A severe cell where the fastest route meets it, plus an optional weaker band elsewhere.

    The main cell is deliberately *on* the fastest route at the truck's ETA, which is the case
    the recommendation logic has to handle. Above ~41°N in winter it brings snow instead of rain.
    """
    month = anchor_eta.month
    cold = anchor[0] > 41 and month in (11, 12, 1, 2, 3)
    storms = [
        Storm(
            lat=anchor[0],
            lon=anchor[1],
            peak_time=anchor_eta.timestamp(),
            peak_rain_in_hr=0.0 if cold else 0.9,
            peak_snow_in_hr=2.6 if cold else 0.0,
        )
    ]
    if secondary and secondary_eta:
        storms.append(
            Storm(
                lat=secondary[0],
                lon=secondary[1],
                peak_time=(secondary_eta + timedelta(hours=3)).timestamp(),
                radius_miles=45,
                heading_deg=100,
                speed_mph=15,
                peak_wind_mph=38,
                peak_rain_in_hr=0.35,
            )
        )
    return SyntheticWeather(storms=tuple(storms))
