"""Open-Meteo hourly forecast (free, no key, multi-location requests)."""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import httpx
from django.core.cache import cache

from ..domain.geometry import LatLon
from ..domain.weather import WeatherSeries
from .base import ProviderError

logger = logging.getLogger(__name__)

HOURLY_VARS = "wind_speed_10m,wind_gusts_10m,rain,showers,snowfall,weather_code"
# 0.01° ≈ 0.7 mi, finer than the forecast models' grids, so rounding loses nothing.
# It also makes nearby requests (shared route prefixes, repeated plans) hit the cache.
COORD_DECIMALS = 2


class OpenMeteoWeather:
    name = "live"

    def __init__(
        self,
        base_url: str = "https://api.open-meteo.com/v1/forecast",
        api_key: str = "",
        batch_size: int = 100,
        max_workers: int = 4,
        cache_seconds: int = 30 * 60,
        timeout: float = 20.0,
    ):
        self.base_url = base_url
        self.api_key = api_key
        self.batch_size = batch_size
        self.max_workers = max_workers
        self.cache_seconds = cache_seconds
        self.timeout = timeout

    def series(self, locations: list[LatLon], start: datetime, end: datetime) -> list[WeatherSeries]:
        start_s, end_s = _hour_param(start), _hour_param(end)
        rounded = [(round(lat, COORD_DECIMALS), round(lon, COORD_DECIMALS)) for lat, lon in locations]
        keys = {loc: f"om:v1:{loc[0]}:{loc[1]}:{start_s}:{end_s}" for loc in set(rounded)}

        found: dict[LatLon, WeatherSeries] = {}
        cached = cache.get_many(list(keys.values()))
        for loc, key in keys.items():
            if key in cached:
                found[loc] = cached[key]

        missing = [loc for loc in keys if loc not in found]
        if missing:
            batches = [missing[i : i + self.batch_size] for i in range(0, len(missing), self.batch_size)]
            with httpx.Client(timeout=self.timeout) as client, ThreadPoolExecutor(self.max_workers) as pool:
                results = pool.map(lambda b: self._fetch(client, b, start_s, end_s), batches)
                fresh = {loc: s for batch_result in results for loc, s in batch_result.items()}
            cache.set_many({keys[loc]: s for loc, s in fresh.items()}, self.cache_seconds)
            found.update(fresh)

        return [found[loc] for loc in rounded]

    def _fetch(self, client: httpx.Client, batch: list[LatLon], start: str, end: str) -> dict[LatLon, WeatherSeries]:
        params = {
            "latitude": ",".join(f"{lat}" for lat, _ in batch),
            "longitude": ",".join(f"{lon}" for _, lon in batch),
            "hourly": HOURLY_VARS,
            "wind_speed_unit": "mph",
            "precipitation_unit": "inch",
            "timeformat": "unixtime",
            "timezone": "GMT",
            "start_hour": start,
            "end_hour": end,
        }
        if self.api_key:
            params["apikey"] = self.api_key
        try:
            response = client.get(self.base_url, params=params)
        except httpx.HTTPError as exc:
            logger.warning("Open-Meteo request failed: %s", exc)
            raise ProviderError("The weather service could not be reached. Please try again.") from exc
        if response.status_code == 429:
            raise ProviderError(
                "The weather service's free-tier limit was reached. Try again shortly, or use simulated weather.",
                429,
            )
        if response.status_code >= 400:
            reason = response.json().get("reason") if "json" in response.headers.get("content-type", "") else ""
            logger.warning("Open-Meteo %s: %s", response.status_code, reason or response.text[:300])
            raise ProviderError(f"Weather service error: {reason or response.status_code}")

        payload = response.json()
        items = payload if isinstance(payload, list) else [payload]
        if len(items) != len(batch):
            raise ProviderError("Weather service returned an unexpected number of locations.")
        return {loc: parse_series(loc, item) for loc, item in zip(batch, items)}


def parse_series(loc: LatLon, item: dict) -> WeatherSeries:
    hourly = item.get("hourly") or {}
    times = hourly.get("time") or []

    def values(name: str) -> list[float]:
        return [float(v) if v is not None else 0.0 for v in hourly.get(name) or [0.0] * len(times)]

    rain, showers = values("rain"), values("showers")
    return WeatherSeries(
        lat=loc[0],
        lon=loc[1],
        times=[int(t) for t in times],
        wind_mph=values("wind_speed_10m"),
        gust_mph=values("wind_gusts_10m"),
        rain_in=[r + s for r, s in zip(rain, showers)],  # liquid rate = stratiform rain + convective showers
        snow_in=values("snowfall"),
        weather_code=list(hourly.get("weather_code") or [None] * len(times)),
    )


def _hour_param(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:00")
