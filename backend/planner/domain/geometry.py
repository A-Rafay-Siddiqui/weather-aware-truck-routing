"""Polyline helpers: distances, interpolation, checkpoint sampling and simplification."""

from __future__ import annotations

import math
from bisect import bisect_left
from dataclasses import dataclass

EARTH_RADIUS_MILES = 3958.7613
METERS_PER_MILE = 1609.344

LatLon = tuple[float, float]


def haversine_miles(a: LatLon, b: LatLon) -> float:
    lat1, lon1 = map(math.radians, a)
    lat2, lon2 = map(math.radians, b)
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * EARTH_RADIUS_MILES * math.asin(min(1.0, math.sqrt(h)))


def cumulative_miles(points: list[LatLon]) -> list[float]:
    """Distance from the start to every vertex."""
    total = 0.0
    out = [0.0]
    for prev, cur in zip(points, points[1:]):
        total += haversine_miles(prev, cur)
        out.append(total)
    return out


def interpolate(xs: list[float], ys: list[float], x: float) -> float:
    """Piecewise-linear interpolation of y(x) for ascending xs, clamped at the ends."""
    if x <= xs[0]:
        return ys[0]
    if x >= xs[-1]:
        return ys[-1]
    i = bisect_left(xs, x)
    x0, x1 = xs[i - 1], xs[i]
    if x1 == x0:
        return ys[i]
    t = (x - x0) / (x1 - x0)
    return ys[i - 1] + t * (ys[i] - ys[i - 1])


def point_at_distance(points: list[LatLon], cum: list[float], miles: float) -> LatLon:
    """The coordinate `miles` along the polyline (linear between vertices)."""
    if miles <= 0:
        return points[0]
    if miles >= cum[-1]:
        return points[-1]
    i = bisect_left(cum, miles)
    d0, d1 = cum[i - 1], cum[i]
    t = 0.0 if d1 == d0 else (miles - d0) / (d1 - d0)
    (lat0, lon0), (lat1, lon1) = points[i - 1], points[i]
    return (lat0 + t * (lat1 - lat0), lon0 + t * (lon1 - lon0))


@dataclass(frozen=True)
class SamplePoint:
    mile: float
    lat: float
    lon: float
    # The stretch of road this sample represents, used to turn risk into "miles at risk".
    segment_start_mile: float
    segment_end_mile: float

    @property
    def segment_miles(self) -> float:
        return self.segment_end_mile - self.segment_start_mile


def sample_checkpoints(points: list[LatLon], cum: list[float], interval_miles: float) -> list[SamplePoint]:
    """Checkpoints at the origin, every `interval_miles`, and the destination.

    Each checkpoint represents the road halfway to its neighbours, so the segments tile the
    whole route exactly and the checkpoint sits in the middle of the miles it is responsible for.
    A final interval mark closer than 10% of an interval to the destination is dropped,
    so the destination doesn't get a near-duplicate checkpoint.
    """
    if interval_miles <= 0:
        raise ValueError("interval_miles must be positive")
    total = cum[-1]
    marks = [0.0]
    k = 1
    while k * interval_miles < total - 0.1 * interval_miles:
        marks.append(k * interval_miles)
        k += 1
    if total > 0:
        marks.append(total)

    samples = []
    for i, mile in enumerate(marks):
        start = 0.0 if i == 0 else (marks[i - 1] + mile) / 2
        end = total if i == len(marks) - 1 else (mile + marks[i + 1]) / 2
        lat, lon = point_at_distance(points, cum, mile)
        samples.append(SamplePoint(mile, lat, lon, start, end))
    return samples


def simplify_indices(points: list[LatLon], tolerance_deg: float) -> list[int]:
    """Douglas–Peucker simplification; returns the indices of the vertices to keep.

    Iterative (no recursion limit issues on 20k+ vertex routes). Distances are measured in a
    locally scaled lon/lat plane, which is plenty accurate for display simplification.
    """
    n = len(points)
    if n <= 2:
        return list(range(n))
    keep = [False] * n
    keep[0] = keep[-1] = True
    stack = [(0, n - 1)]
    tol2 = tolerance_deg**2
    while stack:
        first, last = stack.pop()
        (lat_a, lon_a), (lat_b, lon_b) = points[first], points[last]
        kx = math.cos(math.radians((lat_a + lat_b) / 2))
        ax, ay, bx, by = lon_a * kx, lat_a, lon_b * kx, lat_b
        dx, dy = bx - ax, by - ay
        seg2 = dx * dx + dy * dy
        best_i, best_d2 = -1, tol2
        for i in range(first + 1, last):
            px, py = points[i][1] * kx, points[i][0]
            if seg2 == 0:
                d2 = (px - ax) ** 2 + (py - ay) ** 2
            else:
                t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / seg2))
                d2 = (px - ax - t * dx) ** 2 + (py - ay - t * dy) ** 2
            if d2 > best_d2:
                best_i, best_d2 = i, d2
        if best_i != -1:
            keep[best_i] = True
            stack.append((first, best_i))
            stack.append((best_i, last))
    return [i for i, k in enumerate(keep) if k]


def bbox(points: list[LatLon]) -> tuple[float, float, float, float]:
    """(west, south, east, north)."""
    lats = [p[0] for p in points]
    lons = [p[1] for p in points]
    return (min(lons), min(lats), max(lons), max(lats))


def cell_signature(points: list[LatLon], cell_deg: float = 0.02) -> set[tuple[int, int]]:
    """Set of coarse grid cells a route passes through — used to detect duplicate routes."""
    return {(math.floor(lat / cell_deg), math.floor(lon / cell_deg)) for lat, lon in points}


def overlap_ratio(a: set, b: set) -> float:
    """Share of the smaller signature that is also in the other one."""
    if not a or not b:
        return 0.0
    return len(a & b) / min(len(a), len(b))
