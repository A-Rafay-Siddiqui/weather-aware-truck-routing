"""Trip planning: routes → checkpoints → ETAs → weather → risk → recommendation.

This module is the only place that combines the domain logic with the providers. It returns
a plain JSON-serializable dict: the API stores it as-is and the frontend renders it directly.
"""

from __future__ import annotations

import math
import string
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from ..domain.geometry import (
    METERS_PER_MILE,
    LatLon,
    SamplePoint,
    bbox,
    cumulative_miles,
    point_at_distance,
    sample_checkpoints,
    simplify_indices,
)
from ..domain.ranking import RouteRiskSummary, deciding_criterion, rank_routes
from ..domain.risk import RiskAssessment, RiskLevel, assess
from ..domain.timing import HosPolicy, NoStops, RouteTiming, Stop
from ..providers.base import Place, RouteOption, RoutingProvider, WeatherProvider
from ..providers.synthetic import storms_for_trip

MAX_DISPLAY_POINTS = 1500


@dataclass(frozen=True)
class PlanRequest:
    origin: Place
    destination: Place
    departure: datetime  # timezone-aware
    load_lbs: float
    interval_miles: int
    weather_source: str  # "live" | "simulated"
    include_hos: bool = True


@dataclass
class PreparedRoute:
    """A route with its geometry and timing worked out, before any weather is applied."""

    id: str
    option: RouteOption
    points: list[LatLon]
    cum: list[float]
    timing: RouteTiming
    hos: HosPolicy
    samples: list[SamplePoint]
    sample_drive_s: list[float]
    sample_wall_s: list[float]
    stops: list[Stop]

    @property
    def total_miles(self) -> float:
        return self.cum[-1]

    @property
    def total_drive_s(self) -> float:
        return self.timing.total_drive_seconds

    @property
    def total_wall_s(self) -> float:
        return self.hos.wall_seconds(self.total_drive_s)

    @property
    def name(self) -> str:
        roads = self.option.road_numbers[:2]
        return f"Via {' & '.join(roads)}" if roads else f"Route {self.id} ({self.option.strategy})"


def prepare_route(route_id: str, option: RouteOption, interval_miles: float, hos: HosPolicy) -> PreparedRoute:
    raw = cumulative_miles(option.points)
    # Scale our haversine distances to the provider's official length so all miles agree.
    total = option.length_m / METERS_PER_MILE if option.length_m > 0 else raw[-1]
    scale = total / raw[-1] if raw[-1] > 0 else 1.0
    cum = [d * scale for d in raw]

    timing = RouteTiming(*_timing_knots(option, cum))
    samples = sample_checkpoints(option.points, cum, interval_miles)
    drive = [timing.drive_time_at(s.mile) for s in samples]
    return PreparedRoute(
        id=route_id,
        option=option,
        points=option.points,
        cum=cum,
        timing=timing,
        hos=hos,
        samples=samples,
        sample_drive_s=drive,
        sample_wall_s=[hos.wall_seconds(d) for d in drive],
        stops=hos.stops_before(timing.total_drive_seconds),
    )


def _timing_knots(option: RouteOption, cum: list[float]) -> tuple[list[float], list[float]]:
    """(miles, drive seconds) knots from the provider's per-point progress, kept monotonic."""
    knots = [(0.0, 0.0)]
    for index, seconds in sorted(option.progress):
        if 0 <= index < len(cum):
            mile = cum[index]
            if mile >= knots[-1][0] and seconds >= knots[-1][1]:
                knots.append((mile, seconds))
    end = (cum[-1], max(option.travel_time_s, knots[-1][1]))
    if end[0] > knots[-1][0]:
        knots.append(end)
    elif len(knots) == 1:
        knots.append((max(cum[-1], 1e-6), max(option.travel_time_s, 1.0)))
    return [k[0] for k in knots], [k[1] for k in knots]


def build_plan(request: PlanRequest, routing: RoutingProvider, live_weather: WeatherProvider) -> dict:
    options = routing.routes(request.origin, request.destination, request.departure, request.load_lbs)
    hos = HosPolicy() if request.include_hos else NoStops()
    routes = [
        prepare_route(route_id, option, request.interval_miles, hos)
        for route_id, option in zip(string.ascii_uppercase, options)
    ]

    weather, simulation = _weather_provider(request, routes, live_weather)
    assessments = _assess_checkpoints(request, routes, weather)

    summaries = {
        r.id: RouteRiskSummary.from_segments(
            r.id, [(s.segment_miles, a.level) for s, a in zip(r.samples, assessments[r.id])], r.total_wall_s
        )
        for r in routes
    }
    ranked = rank_routes(list(summaries.values()))
    rank_of = {s.route_id: i + 1 for i, s in enumerate(ranked)}
    best = ranked[0]
    by_id = {r.id: r for r in routes}

    return {
        "request": {
            "origin": request.origin.__dict__,
            "destination": request.destination.__dict__,
            "departure_time": request.departure.isoformat(),
            "load_weight_lbs": request.load_lbs,
            "sample_interval_miles": request.interval_miles,
            "weather_source": request.weather_source,
            "include_hos": request.include_hos,
        },
        "recommended_route_id": best.route_id,
        "recommendation": _explain(best, ranked[1:], by_id),
        "routes": [
            _serialize_route(r, summaries[r.id], assessments[r.id], rank_of[r.id], request.departure) for r in routes
        ],
        "bbox": _union_bbox([bbox(r.points) for r in routes]),
        "simulation": simulation,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def _weather_provider(request: PlanRequest, routes: list[PreparedRoute], live: WeatherProvider):
    if request.weather_source != "simulated":
        return live, None
    anchor_route = routes[0]  # the provider's fastest route
    anchor_mile = anchor_route.total_miles * 0.55
    anchor = point_at_distance(anchor_route.points, anchor_route.cum, anchor_mile)
    anchor_eta = request.departure + timedelta(
        seconds=anchor_route.hos.wall_seconds(anchor_route.timing.drive_time_at(anchor_mile))
    )
    secondary = secondary_eta = None
    if len(routes) > 1:
        other = routes[1]
        mile = other.total_miles * 0.3
        secondary = point_at_distance(other.points, other.cum, mile)
        secondary_eta = request.departure + timedelta(seconds=other.hos.wall_seconds(other.timing.drive_time_at(mile)))
    provider = storms_for_trip(anchor, anchor_eta, secondary, secondary_eta)
    return provider, provider.to_dict()


def forecast_window(departure: datetime, duration_s: float) -> tuple[datetime, datetime]:
    start = departure.astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0)
    end = departure + timedelta(seconds=duration_s)
    end = end.astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0) + timedelta(hours=2)
    return start, end


def _assess_checkpoints(
    request: PlanRequest, routes: list[PreparedRoute], weather: WeatherProvider
) -> dict[str, list[tuple]]:
    """Returns, per route, (conditions, assessment) for every checkpoint at its own ETA."""
    start, end = forecast_window(request.departure, max(r.total_wall_s for r in routes))
    locations = [(s.lat, s.lon) for r in routes for s in r.samples]
    series = iter(weather.series(locations, start, end))
    depart_ts = request.departure.timestamp()

    out: dict[str, list] = {}
    for route in routes:
        rows = []
        for wall in route.sample_wall_s:
            conditions = next(series).at(depart_ts + wall)
            rows.append(_Assessed(conditions, assess(conditions, request.load_lbs)))
        out[route.id] = rows
    return out


@dataclass(frozen=True)
class _Assessed:
    conditions: object
    risk: RiskAssessment

    @property
    def level(self) -> RiskLevel:
        return self.risk.level


def _serialize_route(
    route: PreparedRoute, summary: RouteRiskSummary, assessed: list[_Assessed], rank: int, departure: datetime
) -> dict:
    return {
        "id": route.id,
        "name": route.name,
        "strategy": route.option.strategy,
        "roads": route.option.road_numbers[:4],
        "rank": rank,
        "recommended": rank == 1,
        "distance_miles": round(route.total_miles, 1),
        "drive_time_s": round(route.total_drive_s),
        "travel_time_s": round(route.total_wall_s),
        "traffic_delay_s": round(route.option.traffic_delay_s),
        "departure_time": departure.isoformat(),
        "arrival_time": (departure + timedelta(seconds=route.total_wall_s)).isoformat(),
        "risk": {
            "max_level": summary.max_level.key,
            "average_score": round(summary.average_risk, 3),
            "miles_by_level": {lvl.key: round(summary.miles(lvl), 1) for lvl in RiskLevel},
        },
        "bbox": bbox(route.points),
        "path": _display_path(route),
        "stops": [_serialize_stop(route, stop) for stop in route.stops],
        "checkpoints": [
            _serialize_checkpoint(i, sample, drive, wall, a, departure)
            for i, (sample, drive, wall, a) in enumerate(
                zip(route.samples, route.sample_drive_s, route.sample_wall_s, assessed)
            )
        ],
    }


def _serialize_checkpoint(index, sample: SamplePoint, drive, wall, assessed: _Assessed, departure) -> dict:
    c, risk = assessed.conditions, assessed.risk
    return {
        "index": index,
        "mile": round(sample.mile, 1),
        "lat": round(sample.lat, 5),
        "lon": round(sample.lon, 5),
        "segment": [round(sample.segment_start_mile, 2), round(sample.segment_end_mile, 2)],
        "drive_offset_s": round(drive),
        "eta_offset_s": round(wall),
        "eta": (departure + timedelta(seconds=wall)).isoformat(),
        "weather": {
            "wind_mph": round(c.wind_mph, 1),
            "gust_mph": round(c.gust_mph, 1) if c.gust_mph is not None else None,
            "rain_in_hr": round(c.rain_in_hr, 3),
            "snow_in_hr": round(c.snow_in_hr, 3),
            "weather_code": c.weather_code,
        },
        "risk": {
            "level": risk.level.key,
            "score": risk.score,
            "wind": risk.wind.key,
            "rain": risk.rain.key,
            "snow": risk.snow.key,
            "load_rule_applied": risk.load_rule is not None,
            "factors": list(risk.factors),
        },
    }


def _serialize_stop(route: PreparedRoute, stop: Stop) -> dict:
    mile = route.timing.mile_at(stop.drive_seconds)
    lat, lon = point_at_distance(route.points, route.cum, mile)
    return {
        "kind": stop.kind,
        "mile": round(mile, 1),
        "lat": round(lat, 5),
        "lon": round(lon, 5),
        "start_offset_s": round(route.hos.wall_seconds(stop.drive_seconds)),
        "duration_s": round(stop.duration_seconds),
    }


def _display_path(route: PreparedRoute) -> list[list[float]]:
    """Simplified [lon, lat, seconds-after-departure, mile] vertices for drawing and animating the truck.

    Each stop is inserted twice (arrival and departure at the same spot), so interpolating
    position by time on the client keeps the truck parked for the length of the stop.
    """
    tolerance = 0.0003
    keep = simplify_indices(route.points, tolerance)
    while len(keep) > MAX_DISPLAY_POINTS:
        tolerance *= 2
        keep = simplify_indices(route.points, tolerance)

    knots = []
    for i in keep:
        mile = route.cum[i]
        wall = route.hos.wall_seconds(route.timing.drive_time_at(mile))
        lat, lon = route.points[i]
        knots.append((mile, wall, lon, lat))
    for stop in route.stops:
        mile = route.timing.mile_at(stop.drive_seconds)
        lat, lon = point_at_distance(route.points, route.cum, mile)
        start = route.hos.wall_seconds(stop.drive_seconds)
        knots.append((mile, start, lon, lat))
        knots.append((mile, start + stop.duration_seconds, lon, lat))
    knots.sort(key=lambda k: (k[0], k[1]))
    return [[round(lon, 5), round(lat, 5), round(wall), round(mile, 2)] for mile, wall, lon, lat in knots]


def _explain(best: RouteRiskSummary, others: list[RouteRiskSummary], routes: dict[str, PreparedRoute]) -> dict:
    winner = routes[best.route_id]
    reasons = []
    for other in others:
        criterion = deciding_criterion(best, other)
        label = f"Route {other.route_id} ({routes[other.route_id].name})"
        if criterion is None:
            reasons.append(f"Ties with {label} on every criterion; kept the faster-listed option.")
            continue
        detail = _compare(criterion.key, best, other)
        if criterion.key == "travel_time":
            reasons.append(f"Same weather risk as {label}, but faster: {detail}.")
        else:
            reasons.append(
                f"Fewer {criterion.label} than {label}: {detail}."
                if criterion.key.endswith("miles")
                else f"Lower {criterion.label} than {label}: {detail}."
            )

    warnings = []
    nt, severe, high = (best.miles(RiskLevel.NO_TRAVEL), best.miles(RiskLevel.SEVERE), best.miles(RiskLevel.HIGH))
    if nt > 0:
        warnings.append(
            f"Every route crosses No Travel conditions; even the best has {nt:.0f} No Travel miles. "
            "Consider delaying departure."
        )
    elif severe > 0:
        warnings.append(f"The recommended route still has {severe:.0f} Severe miles. Drive with extreme caution.")
    elif high > 0:
        warnings.append(f"The recommended route has {high:.0f} miles of High risk weather.")

    return {
        "route_id": best.route_id,
        "headline": f"Take Route {best.route_id}: {winner.name}",
        "reasons": reasons,
        "warnings": warnings,
        "criteria": ["No Travel miles", "Severe miles", "High miles", "Average risk", "Travel time"],
    }


def _compare(key: str, a: RouteRiskSummary, b: RouteRiskSummary) -> str:
    if key == "no_travel_miles":
        return f"{a.miles(RiskLevel.NO_TRAVEL):.0f} vs {b.miles(RiskLevel.NO_TRAVEL):.0f} mi"
    if key == "severe_miles":
        return f"{a.miles(RiskLevel.SEVERE):.0f} vs {b.miles(RiskLevel.SEVERE):.0f} mi"
    if key == "high_miles":
        return f"{a.miles(RiskLevel.HIGH):.0f} vs {b.miles(RiskLevel.HIGH):.0f} mi"
    if key == "average_risk":
        return f"{a.average_risk:.2f} vs {b.average_risk:.2f} on a 0–4 scale"
    return f"{format_duration(a.travel_seconds)} vs {format_duration(b.travel_seconds)}"


def format_duration(seconds: float) -> str:
    minutes = int(math.floor(seconds / 60 + 0.5))
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes:02d}m" if hours else f"{minutes}m"


def _union_bbox(boxes: list[tuple[float, float, float, float]]) -> list[float]:
    return [min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes)]
