"""Open-Meteo hourly forecast (free, no key, multi-location requests).

The free tier allows 600 calls per minute, and every location in a multi-location request
counts as one call. A long trip sampled every 10 mi, plus its heatmap, can spend that in one
go, so this provider works to keep the call count down:

* **Snapping.** Points snap to a 0.05° lattice (≈3.5 mi). That is still finer than the 3 km
  HRRR model Open-Meteo uses over the U.S., but it lets overlapping routes and repeat plans
  share forecasts.
* **Departure-independent caching.** Each point's forecast is fetched for a fixed window
  starting at the current hour (3, 7 or 11 days). A cached forecast then serves any plan,
  whatever its departure time.
* **Shared per-minute budget.** The budget is counted in the cache (Redis in production), so
  all workers share it. A request that would exceed it waits for the next minute instead
  of failing, and a stray 429 is retried once after that wait.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import httpx
from django.core.cache import cache

from ..domain.geometry import LatLon
from ..domain.weather import WeatherSeries
from .base import ProviderError

logger = logging.getLogger(__name__)

HOURLY_VARS = "wind_speed_10m,wind_gusts_10m,rain,showers,snowfall,weather_code"
SNAP_DEG = 0.05
HORIZONS_HOURS = (72, 168, 264)  # fixed windows → stable cache keys; all well under the 2-week "multiple calls" rule


def snap(loc: LatLon) -> LatLon:
    return (round(round(loc[0] / SNAP_DEG) * SNAP_DEG, 2), round(round(loc[1] / SNAP_DEG) * SNAP_DEG, 2))


def forecast_window(end: datetime, now: datetime | None = None) -> tuple[datetime, datetime]:
    """Smallest fixed window starting at the current hour that reaches `end`."""
    start = (now or datetime.now(timezone.utc)).astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0)
    for hours in HORIZONS_HOURS:
        if start + timedelta(hours=hours) >= end:
            return start, start + timedelta(hours=hours)
    return start, end.astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)


class MinuteBudget:
    """Locations requested per clock minute, counted in the shared cache."""

    def __init__(
        self,
        limit: int,
        clock: Callable[[], float] = time.time,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.limit = limit
        self.clock = clock
        self.sleep = sleep

    def seconds_to_next_minute(self) -> float:
        return 60 - (self.clock() % 60) + 0.5

    def acquire(self, n: int, deadline: float) -> None:
        """Reserve `n` calls, waiting for the next minute if needed; raises past `deadline`."""
        while True:
            key = f"om:budget:{int(self.clock() // 60)}"
            cache.add(key, 0, timeout=120)
            try:
                used = cache.incr(key, n)
            except ValueError:  # key evicted between add and incr
                cache.set(key, n, timeout=120)
                used = n
            if used <= self.limit:
                return
            cache.decr(key, n)
            self.wait_for_next_minute(deadline)

    def wait_for_next_minute(self, deadline: float) -> None:
        wait = self.seconds_to_next_minute()
        if self.clock() + wait > deadline:
            raise ProviderError(
                "The free weather service is at its per-minute limit. Please try again in a minute, or use Simulation.",
                429,
            )
        logger.info("Open-Meteo budget exhausted; waiting %.0fs", wait)
        self.sleep(wait)


class OpenMeteoWeather:
    name = "live"

    def __init__(
        self,
        base_url: str = "https://api.open-meteo.com/v1/forecast",
        api_key: str = "",
        per_minute: int = 500,
        max_wait_seconds: float = 65,
        batch_size: int = 100,
        max_workers: int = 4,
        timeout: float = 20.0,
        budget: MinuteBudget | None = None,
    ):
        self.base_url = base_url
        self.api_key = api_key
        self.max_wait_seconds = max_wait_seconds
        self.batch_size = batch_size
        self.max_workers = max_workers
        self.timeout = timeout
        self.budget = budget or MinuteBudget(per_minute)

    def series(self, locations: list[LatLon], start: datetime, end: datetime) -> list[WeatherSeries]:
        w_start, w_end = forecast_window(end)
        start_s, end_s = _hour_param(w_start), _hour_param(w_end)
        snapped = [snap(loc) for loc in locations]
        keys = {loc: f"om:v2:{loc[0]}:{loc[1]}:{start_s}:{end_s}" for loc in set(snapped)}

        cached = cache.get_many(list(keys.values()))
        found: dict[LatLon, WeatherSeries] = {loc: cached[key] for loc, key in keys.items() if key in cached}

        missing = [loc for loc in keys if loc not in found]
        if missing:
            deadline = self.budget.clock() + self.max_wait_seconds
            batches = [missing[i : i + self.batch_size] for i in range(0, len(missing), self.batch_size)]
            with httpx.Client(timeout=self.timeout) as client, ThreadPoolExecutor(self.max_workers) as pool:
                results = pool.map(lambda b: self._fetch(client, b, start_s, end_s, deadline), batches)
                fresh = {loc: s for batch_result in results for loc, s in batch_result.items()}
            # Keys change every hour (window start), which matches how often the models update.
            cache.set_many({keys[loc]: s for loc, s in fresh.items()}, 70 * 60)
            found.update(fresh)

        return [found[loc] for loc in snapped]

    def _fetch(
        self, client: httpx.Client, batch: list[LatLon], start: str, end: str, deadline: float
    ) -> dict[LatLon, WeatherSeries]:
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

        for attempt in range(2):
            self.budget.acquire(len(batch), deadline)
            try:
                response = client.get(self.base_url, params=params)
            except httpx.HTTPError as exc:
                logger.warning("Open-Meteo request failed: %s", exc)
                raise ProviderError("The weather service could not be reached. Please try again.") from exc
            if response.status_code == 429 and attempt == 0:
                # Another client on our IP may share the quota: wait out this minute once.
                self.budget.wait_for_next_minute(deadline)
                continue
            break

        if response.status_code == 429:
            raise ProviderError(
                "The free weather service is at its rate limit. Please try again in a minute, or use Simulation.",
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
