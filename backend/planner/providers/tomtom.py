"""TomTom Routing (truck profile) and Search APIs."""

from __future__ import annotations

import logging
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

import httpx
from django.core.cache import cache

from ..domain.geometry import METERS_PER_MILE, cell_signature, cumulative_miles, overlap_ratio
from .base import NoRouteFound, Place, ProviderError, RouteOption

logger = logging.getLogger(__name__)

BASE_URL = "https://api.tomtom.com"
LBS_TO_KG = 0.45359237
# The user enters cargo weight; TomTom wants gross vehicle weight for restrictions.
TRACTOR_TRAILER_TARE_LBS = 35_000
TARGET_ROUTES = 3
# Two candidates sharing this much of their path count as the same route.
DUPLICATE_OVERLAP = 0.9


class TomTomClient:
    def __init__(self, api_key: str, timeout: float = 20.0, client: httpx.Client | None = None):
        if not api_key:
            raise ProviderError("TOMTOM_API_KEY is not configured on the server.", status_code=503)
        self.api_key = api_key
        self.http = client or httpx.Client(base_url=BASE_URL, timeout=timeout)

    def get(self, path: str, params: list[tuple[str, str | int]]) -> dict:
        try:
            response = self.http.get(path, params=[("key", self.api_key), *params])
        except httpx.HTTPError as exc:
            logger.warning("TomTom request failed: %s", exc)
            raise ProviderError("The routing service could not be reached. Please try again.") from exc
        if response.status_code == 429:
            raise ProviderError("Routing rate limit reached. Please wait a moment and retry.", 429)
        if response.status_code >= 400:
            raise _error_from(response)
        return response.json()


def _error_from(response: httpx.Response) -> ProviderError:
    try:
        body = response.json()
        detail = (body.get("error") or {}).get("description") or (body.get("detailedError") or {}).get("message")
    except ValueError:
        detail = None
    logger.warning("TomTom %s: %s", response.status_code, detail or response.text[:300])
    if response.status_code == 400 and detail and "route" in detail.lower():
        return NoRouteFound(f"No truck route found: {detail}")
    if response.status_code in (401, 403):
        return ProviderError("The routing API key was rejected by TomTom.", 503)
    return ProviderError(f"Routing service error: {detail or response.status_code}")


class TomTomRouting:
    """Truck routes with alternatives.

    One request asks for the fastest route plus `maxAlternatives=2`. TomTom may return fewer
    alternatives, for example on short trips. In that case we also ask for routes under other
    strategies (avoid tolls, eco, short) and keep the ones that really differ.
    """

    FALLBACK_STRATEGIES: tuple[tuple[str, list[tuple[str, str]]], ...] = (
        ("avoid tolls", [("avoid", "tollRoads")]),
        ("eco", [("routeType", "eco")]),
        ("short", [("routeType", "short")]),
    )

    def __init__(self, client: TomTomClient):
        self.client = client

    CACHE_SECONDS = 10 * 60

    def routes(self, origin: Place, destination: Place, depart_at: datetime, load_lbs: float) -> list[RouteOption]:
        # Computing alternatives takes TomTom ~4 s on long trips. Identical requests within the
        # same departure hour reuse the result (repeat plans, toggling the interval or weather source).
        key = (
            f"tt:routes:v1:{origin.lat:.4f},{origin.lon:.4f}:{destination.lat:.4f},{destination.lon:.4f}:"
            f"{round(load_lbs, -3):.0f}:{_depart_at_param(depart_at)[:13]}"
        )
        cached = cache.get(key)
        if cached is not None:
            return cached
        options = self._routes(origin, destination, depart_at, load_lbs)
        cache.set(key, options, self.CACHE_SECONDS)
        return options

    def _routes(self, origin: Place, destination: Place, depart_at: datetime, load_lbs: float) -> list[RouteOption]:
        primary = self._calculate(origin, destination, depart_at, load_lbs, [("maxAlternatives", TARGET_ROUTES - 1)])
        if not primary:
            raise NoRouteFound()
        primary[0].strategy = "fastest"
        for alt in primary[1:]:
            alt.strategy = "alternative"
        options = self._dedupe(primary)
        if len(options) >= TARGET_ROUTES:
            return options[:TARGET_ROUTES]

        with ThreadPoolExecutor(max_workers=len(self.FALLBACK_STRATEGIES)) as pool:
            futures = [
                (name, pool.submit(self._calculate, origin, destination, depart_at, load_lbs, params))
                for name, params in self.FALLBACK_STRATEGIES
            ]
            for name, future in futures:
                try:
                    for option in future.result():
                        option.strategy = name
                        options = self._dedupe([*options, option])
                except ProviderError as exc:  # a failed fallback is not fatal
                    logger.info("Fallback strategy %s failed: %s", name, exc.message)
                if len(options) >= TARGET_ROUTES:
                    break
        return options[:TARGET_ROUTES]

    def _calculate(
        self, origin: Place, destination: Place, depart_at: datetime, load_lbs: float, extra: list[tuple[str, str]]
    ) -> list[RouteOption]:
        gross_kg = round((load_lbs + TRACTOR_TRAILER_TARE_LBS) * LBS_TO_KG)
        params: list[tuple[str, str | int]] = [
            ("travelMode", "truck"),
            ("vehicleWeight", gross_kg),
            ("vehicleCommercial", "true"),
            ("traffic", "true"),
            ("departAt", _depart_at_param(depart_at)),
            ("routeRepresentation", "polyline"),
            ("extendedRouteRepresentation", "distance"),
            ("extendedRouteRepresentation", "travelTime"),
            ("sectionType", "importantRoadStretch"),
            *extra,
        ]
        if not any(k == "routeType" for k, _ in extra):
            params.append(("routeType", "fastest"))
        path = (
            f"/routing/1/calculateRoute/{origin.lat:.6f},{origin.lon:.6f}:"
            f"{destination.lat:.6f},{destination.lon:.6f}/json"
        )
        data = self.client.get(path, params)
        return [parse_route(r) for r in data.get("routes", [])]

    @staticmethod
    def _dedupe(options: list[RouteOption]) -> list[RouteOption]:
        kept: list[tuple[RouteOption, set]] = []
        for option in options:
            sig = cell_signature(option.points)
            if all(overlap_ratio(sig, other) < DUPLICATE_OVERLAP for _, other in kept):
                kept.append((option, sig))
        return [o for o, _ in kept]


def _depart_at_param(depart_at: datetime) -> str:
    # TomTom rejects departure times in the past; anything within a minute of now is "now".
    if depart_at <= datetime.now(timezone.utc) + timedelta(minutes=1):
        return "now"
    return depart_at.astimezone(timezone.utc).isoformat(timespec="seconds")


def parse_route(route: dict) -> RouteOption:
    points = [(p["latitude"], p["longitude"]) for leg in route.get("legs", []) for p in leg.get("points", [])]
    if len(points) < 2:
        raise ProviderError("Routing service returned a route without geometry.")
    summary = route.get("summary", {})
    progress = [
        (int(p["pointIndex"]), float(p["travelTimeInSeconds"]))
        for p in route.get("progress", [])
        if "pointIndex" in p and "travelTimeInSeconds" in p
    ]
    return RouteOption(
        points=points,
        length_m=float(summary.get("lengthInMeters", 0)),
        travel_time_s=float(summary.get("travelTimeInSeconds", 0)),
        traffic_delay_s=float(summary.get("trafficDelayInSeconds", 0)),
        progress=progress,
        road_numbers=_main_roads(route.get("sections", []), points),
    )


def _main_roads(sections: list[dict], points: list) -> list[str]:
    """Road numbers ordered by how many miles of the route they carry (e.g. ["I-80", "I-76"])."""
    cum = None
    miles_by_road: dict[str, float] = defaultdict(float)
    for section in sections:
        if section.get("sectionType") != "IMPORTANT_ROAD_STRETCH":
            continue
        numbers = [n.get("text") for n in section.get("roadNumbers", []) if n.get("text")]
        if not numbers:
            continue
        cum = cum or cumulative_miles(points)
        start = min(section.get("startPointIndex", 0), len(cum) - 1)
        end = min(section.get("endPointIndex", start), len(cum) - 1)
        miles_by_road[numbers[0]] += cum[end] - cum[start]
    return [road for road, _ in sorted(miles_by_road.items(), key=lambda kv: -kv[1])]


class TomTomGeocoder:
    CACHE_SECONDS = 24 * 3600

    def __init__(self, client: TomTomClient, country_set: str = "US,CA"):
        self.client = client
        self.country_set = country_set

    def search(self, query: str) -> list[Place]:
        query = query.strip()
        if len(query) < 2:
            return []
        key = f"geocode:v1:{self.country_set}:{query.lower()}"
        cached = cache.get(key)
        if cached is not None:
            return [Place(**p) for p in cached]
        data = self.client.get(
            f"/search/2/search/{quote(query, safe='')}.json",
            [("typeahead", "true"), ("limit", 6), ("countrySet", self.country_set)],
        )
        places = [_place_from(result) for result in data.get("results", [])]
        places = [p for p in places if p]
        cache.set(key, [p.__dict__ for p in places], self.CACHE_SECONDS)
        return places


def _place_from(result: dict) -> Place | None:
    position = result.get("position") or {}
    if "lat" not in position or "lon" not in position:
        return None
    address = result.get("address") or {}
    label = address.get("freeformAddress") or ""
    poi_name = (result.get("poi") or {}).get("name")
    if poi_name:
        label = f"{poi_name}, {label}" if label else poi_name
    return Place(
        label=label or f"{position['lat']:.4f}, {position['lon']:.4f}", lat=position["lat"], lon=position["lon"]
    )


def meters_to_miles(meters: float) -> float:
    return meters / METERS_PER_MILE
