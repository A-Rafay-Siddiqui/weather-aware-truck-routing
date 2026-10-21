"""Weather heatmap along the trip corridor, 0–48 h after departure.

The grid is square in Web Mercator: columns are evenly spaced in longitude and rows evenly
spaced in Mercator y. That makes it a plain image on the map, so the frontend draws each
hour as a tiny bitmap and the GPU stretches and smooths it for free. Only cells within the
corridor around the routes are fetched, and the grid spacing adapts to the trip length so
any trip stays under a fixed weather-API budget.

All 49 hourly frames are returned in one response. Moving the slider never hits the network.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

from ..domain.geometry import cumulative_miles, point_at_distance
from ..domain.risk import Conditions, assess
from ..providers.base import WeatherProvider

HOURS = 48
MAX_CELLS = 320
CORRIDOR_MILES = 45
CELL_SIZES_DEG = (0.1, 0.125, 0.15, 0.2, 0.25, 0.3, 0.35, 0.4, 0.45, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.25, 1.5)


def merc_y(lat: float) -> float:
    """Mercator y expressed in degrees, so it shares units with longitude."""
    return math.degrees(math.log(math.tan(math.pi / 4 + math.radians(lat) / 2)))


def inv_merc_y(y: float) -> float:
    return math.degrees(2 * math.atan(math.exp(math.radians(y))) - math.pi / 2)


def _densify(path: list[tuple[float, float]], step_miles: float) -> list[tuple[float, float]]:
    """Points every `step_miles` along a (lat, lon) path, so straight segments still mark every cell they cross."""
    cum = cumulative_miles(path)
    n = max(2, int(cum[-1] / step_miles) + 2)
    return [point_at_distance(path, cum, cum[-1] * i / (n - 1)) for i in range(n)]


def corridor_cells(paths: list[list[tuple[float, float]]], cell_deg: float) -> set[tuple[int, int]]:
    """Global (col, row) indices of cells within CORRIDOR_MILES of any route."""
    cells: set[tuple[int, int]] = set()
    step = cell_deg * 69 * 0.5
    for path in paths:
        for lat, lon in _densify(path, step):
            # One mile spans more Mercator degrees farther from the equator.
            radius_deg = CORRIDOR_MILES / 69.0 / math.cos(math.radians(lat))
            r = max(1, math.ceil(radius_deg / cell_deg))
            ci, cj = math.floor(lon / cell_deg), math.floor(merc_y(lat) / cell_deg)
            for di in range(-r, r + 1):
                for dj in range(-r, r + 1):
                    if di * di + dj * dj <= r * r:
                        cells.add((ci + di, cj + dj))
    return cells


def choose_grid(paths: list[list[tuple[float, float]]]) -> tuple[float, set[tuple[int, int]]]:
    """Finest cell size whose corridor fits in MAX_CELLS.

    Starts from an area estimate (corridor length × width ÷ budget), so long trips don't
    spend time building grids that are obviously too fine.
    """
    longest = max(cumulative_miles(p)[-1] for p in paths)
    est_cell_miles = math.sqrt(longest * 1.5 * 2 * CORRIDOR_MILES / MAX_CELLS)
    candidates = [s for s in CELL_SIZES_DEG if s * 69 >= est_cell_miles * 0.6] or [CELL_SIZES_DEG[-1]]
    for size in candidates:
        cells = corridor_cells(paths, size)
        if len(cells) <= MAX_CELLS:
            return size, cells
    return CELL_SIZES_DEG[-1], corridor_cells(paths, CELL_SIZES_DEG[-1])


def build_heatmap(
    paths: list[list[tuple[float, float]]], departure: datetime, load_lbs: float, weather: WeatherProvider
) -> dict:
    """`paths` are (lat, lon) route geometries; the result is a compact JSON grid."""
    size, cells = choose_grid(paths)
    cols = [c for c, _ in cells]
    rows = [r for _, r in cells]
    c0, c1, r0, r1 = min(cols), max(cols), min(rows), max(rows)
    ordered = sorted(cells, key=lambda cr: (-cr[1], cr[0]))  # north-to-south, west-to-east
    centers = [(inv_merc_y((r + 0.5) * size), (c + 0.5) * size) for c, r in ordered]

    start = departure.astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0)
    if start < departure:
        start += timedelta(hours=1)  # frame 0 is the first whole hour at or after departure
    series = weather.series(centers, start, start + timedelta(hours=HOURS))
    hours = [start.timestamp() + h * 3600 for h in range(HOURS + 1)]

    wind, rain, snow, risk = [], [], [], []
    for s in series:
        conds: list[Conditions] = [s.at(t) for t in hours]
        wind.append([round(c.wind_mph) for c in conds])
        rain.append([round(c.rain_in_hr, 2) for c in conds])
        snow.append([round(c.snow_in_hr, 2) for c in conds])
        risk.append([assess(c, load_lbs).score for c in conds])

    return {
        "cell_deg": size,
        "cols": c1 - c0 + 1,
        "rows": r1 - r0 + 1,
        # Outer edges of the grid. The image corners are exact in Mercator.
        "west": c0 * size,
        "east": (c1 + 1) * size,
        "north": inv_merc_y((r1 + 1) * size),
        "south": inv_merc_y(r0 * size),
        "start_time": start.isoformat(),
        "hours": HOURS + 1,
        # [x, y] position in the image (0,0 = north-west), parallel to the value arrays.
        "cells": [[c - c0, r1 - r] for c, r in ordered],
        "centers": [[round(lat, 4), round(lon, 4)] for lat, lon in centers],
        "wind_mph": wind,
        "rain_in_hr": rain,
        "snow_in_hr": snow,
        "risk": risk,
    }
