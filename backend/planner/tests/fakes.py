"""Test doubles: a routing provider with three hand-made routes and calm/stormy weather."""

from __future__ import annotations

from planner.domain.geometry import cumulative_miles
from planner.domain.weather import WeatherSeries
from planner.providers.base import Place, RouteOption

ORIGIN = Place("Chicago, IL", 41.8781, -87.6298)
DESTINATION = Place("Des Moines, IA", 41.5868, -93.6250)


def _path(via_lat: float, n: int = 120):
    """Two straight legs: origin → (via_lat, midpoint lon) → destination."""
    mid_lon = (ORIGIN.lon + DESTINATION.lon) / 2
    legs = [(ORIGIN.lat, ORIGIN.lon), (via_lat, mid_lon), (DESTINATION.lat, DESTINATION.lon)]
    pts = []
    for (a_lat, a_lon), (b_lat, b_lon) in zip(legs, legs[1:]):
        for i in range(n):
            t = i / n
            pts.append((a_lat + (b_lat - a_lat) * t, a_lon + (b_lon - a_lon) * t))
    pts.append(legs[-1])
    return pts


def make_option(via_lat: float, mph: float, strategy: str, roads: list[str]) -> RouteOption:
    pts = _path(via_lat)
    cum = cumulative_miles(pts)
    progress = [(i, cum[i] / mph * 3600) for i in range(0, len(pts), 10)] + [(len(pts) - 1, cum[-1] / mph * 3600)]
    return RouteOption(
        points=pts,
        length_m=cum[-1] * 1609.344,
        travel_time_s=cum[-1] / mph * 3600,
        progress=progress,
        road_numbers=roads,
        strategy=strategy,
    )


class FakeRouting:
    """A = fastest (straight), B = north detour, C = south detour (slower)."""

    def __init__(self):
        self.calls = []

    def routes(self, origin, destination, depart_at, load_lbs):
        self.calls.append((origin, destination, depart_at, load_lbs))
        return [
            make_option(41.73, 62, "fastest", ["I-80"]),
            make_option(42.9, 58, "alternative", ["I-90", "I-35"]),
            make_option(40.6, 55, "alternative", ["US-34"]),
        ]


class CalmWeather:
    name = "live"

    def __init__(self, wind=8.0, rain=0.0, snow=0.0):
        self.wind, self.rain, self.snow = wind, rain, snow
        self.requested = []

    def series(self, locations, start, end):
        self.requested.append((len(locations), start, end))
        t0, t1 = int(start.timestamp()), int(end.timestamp())
        times = list(range(t0, t1 + 3600, 3600))
        n = len(times)
        return [
            WeatherSeries(
                lat, lon, times, [self.wind] * n, [self.wind * 1.3] * n, [self.rain] * n, [self.snow] * n, [0] * n
            )
            for lat, lon in locations
        ]
