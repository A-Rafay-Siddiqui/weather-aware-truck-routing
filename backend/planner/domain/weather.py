"""Hourly forecast series for one location and lookup at an arbitrary time."""

from __future__ import annotations

from bisect import bisect_left
from dataclasses import dataclass

from .geometry import interpolate
from .risk import Conditions


@dataclass(frozen=True)
class WeatherSeries:
    """Hourly values, aligned with `times` (unix seconds, UTC, ascending).

    Precipitation values are the total over the *preceding* hour (Open-Meteo convention),
    so each one is already a rate in in/hr. Wind is an instantaneous value at the hour.
    """

    lat: float
    lon: float
    times: list[int]
    wind_mph: list[float]
    gust_mph: list[float]
    rain_in: list[float]
    snow_in: list[float]
    weather_code: list[int | None]

    def covers(self, t: float) -> bool:
        return bool(self.times) and self.times[0] <= t <= self.times[-1]

    def at(self, t: float) -> Conditions:
        """Conditions at unix time `t`.

        Wind is interpolated linearly between hours. Precipitation comes from the hour whose
        preceding-hour window contains `t` (the first sample at or after `t`), so 14:20 uses the
        14:00–15:00 total stamped 15:00. Times outside the series are clamped to the ends.
        """
        if not self.times:
            raise ValueError("empty weather series")
        idx = min(bisect_left(self.times, t), len(self.times) - 1)
        return Conditions(
            wind_mph=interpolate(self.times, self.wind_mph, t),
            gust_mph=interpolate(self.times, self.gust_mph, t),
            rain_in_hr=self.rain_in[idx],
            snow_in_hr=self.snow_in[idx],
            weather_code=self.weather_code[idx],
        )
