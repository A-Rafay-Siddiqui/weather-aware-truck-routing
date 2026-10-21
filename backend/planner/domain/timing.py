"""Turning distance along a route into an arrival time.

Two layers:

1. `RouteTiming` maps distance → *driving* time using the routing provider's own
   per-point progress (traffic-aware for the departure time), interpolated linearly.
2. `HosPolicy` maps driving time → *wall-clock* time by inserting the U.S. FMCSA
   Hours-of-Service stops for property-carrying drivers (simplified): a 30-minute break
   after 8 cumulative hours of driving and a 10-hour off-duty rest after 11 hours.
   On long hauls this shifts ETAs by many hours, which changes which weather the truck
   actually meets.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .geometry import interpolate

HOUR = 3600


@dataclass(frozen=True)
class RouteTiming:
    """Monotonic (miles, driving seconds) knots for one route."""

    miles: list[float]
    drive_seconds: list[float]

    def __post_init__(self):
        if len(self.miles) != len(self.drive_seconds) or len(self.miles) < 2:
            raise ValueError("RouteTiming needs at least two matching knots")

    @property
    def total_drive_seconds(self) -> float:
        return self.drive_seconds[-1]

    def drive_time_at(self, mile: float) -> float:
        return interpolate(self.miles, self.drive_seconds, mile)

    def mile_at(self, drive_seconds: float) -> float:
        return interpolate(self.drive_seconds, self.miles, drive_seconds)


@dataclass(frozen=True)
class Stop:
    kind: str  # "break" | "rest"
    drive_seconds: float  # cumulative driving time when the stop starts
    duration_seconds: float


@dataclass(frozen=True)
class HosPolicy:
    break_after_s: float = 8 * HOUR
    break_duration_s: float = 0.5 * HOUR
    rest_after_s: float = 11 * HOUR
    rest_duration_s: float = 10 * HOUR

    def stops_before(self, drive_seconds: float) -> list[Stop]:
        """All stops that start strictly before `drive_seconds` of driving.

        A stop scheduled exactly at the end of the trip isn't taken, since the driver has arrived.
        """
        stops: list[Stop] = []
        block_start = 0.0
        while block_start < drive_seconds:
            block_end = block_start + self.rest_after_s
            t = block_start + self.break_after_s
            while t < min(block_end, drive_seconds):
                stops.append(Stop("break", t, self.break_duration_s))
                t += self.break_after_s
            if block_end < drive_seconds:
                stops.append(Stop("rest", block_end, self.rest_duration_s))
            block_start = block_end
        return stops

    def wall_seconds(self, drive_seconds: float) -> float:
        """Elapsed wall-clock time when the truck has driven `drive_seconds`."""
        if drive_seconds <= 0:
            return 0.0
        full_blocks = math.ceil(drive_seconds / self.rest_after_s) - 1
        in_block = drive_seconds - full_blocks * self.rest_after_s
        breaks_per_block = math.ceil(self.rest_after_s / self.break_after_s) - 1
        breaks_now = math.ceil(in_block / self.break_after_s) - 1
        return (
            drive_seconds
            + full_blocks * (self.rest_duration_s + breaks_per_block * self.break_duration_s)
            + breaks_now * self.break_duration_s
        )


class NoStops(HosPolicy):
    """Used when the user turns HOS off: wall time equals driving time."""

    def stops_before(self, drive_seconds: float) -> list[Stop]:
        return []

    def wall_seconds(self, drive_seconds: float) -> float:
        return max(0.0, drive_seconds)
