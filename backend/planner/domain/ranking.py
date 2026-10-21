"""Route-level risk aggregation and the recommendation ordering.

The spec's preference order is:
  1. fewest Severe miles  2. fewest High miles  3. lowest average risk  4. shortest travel time

Two interpretation choices, both documented in the README:

* No Travel is stricter than Severe, so No Travel miles are compared *before* Severe miles.
  Otherwise a route with 5 No Travel miles would beat a route with 6 Severe miles.
* Average risk is mile-weighted (Low=0 … No Travel=4). Any route within 0.1 of the lowest
  average counts as tied with it, in 0.1-wide bands measured from that lowest value. With
  exact floats, travel time would almost never break a tie and the recommendation would
  add hours of driving to avoid a few Moderate miles. Measuring bands from the best route,
  rather than rounding, means 0.33 vs 0.36 is a tie instead of landing on either side of a
  fixed 0.35 boundary.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from .risk import RiskLevel

AVG_RISK_RESOLUTION = 0.1
MILES_RESOLUTION = 0.1


@dataclass
class RouteRiskSummary:
    route_id: str
    total_miles: float
    travel_seconds: float
    miles_by_level: dict[RiskLevel, float] = field(default_factory=dict)

    @classmethod
    def from_segments(
        cls, route_id: str, segments: list[tuple[float, RiskLevel]], travel_seconds: float
    ) -> RouteRiskSummary:
        """`segments` is (miles, level) for each checkpoint's stretch of road."""
        miles_by_level = {level: 0.0 for level in RiskLevel}
        for miles, level in segments:
            miles_by_level[level] += miles
        return cls(route_id, sum(m for m, _ in segments), travel_seconds, miles_by_level)

    def miles(self, level: RiskLevel) -> float:
        return self.miles_by_level.get(level, 0.0)

    @property
    def average_risk(self) -> float:
        if self.total_miles <= 0:
            return 0.0
        return sum(int(lvl) * m for lvl, m in self.miles_by_level.items()) / self.total_miles

    @property
    def max_level(self) -> RiskLevel:
        present = [lvl for lvl, m in self.miles_by_level.items() if m > 0]
        return max(present) if present else RiskLevel.LOW

    def sort_key(self, avg_anchor: float = 0.0) -> tuple:
        """Lexicographic key; `avg_anchor` is the lowest average risk among the routes compared."""

        def q(value: float) -> int:
            return round(value / MILES_RESOLUTION)

        return (
            q(self.miles(RiskLevel.NO_TRAVEL)),
            q(self.miles(RiskLevel.SEVERE)),
            q(self.miles(RiskLevel.HIGH)),
            math.floor((self.average_risk - avg_anchor) / AVG_RISK_RESOLUTION + 1e-9),
            self.travel_seconds,
        )


@dataclass(frozen=True)
class Criterion:
    key: str
    label: str


CRITERIA = (
    Criterion("no_travel_miles", "No Travel miles"),
    Criterion("severe_miles", "Severe miles"),
    Criterion("high_miles", "High miles"),
    Criterion("average_risk", "average risk"),
    Criterion("travel_time", "travel time"),
)


def average_anchor(summaries: list[RouteRiskSummary]) -> float:
    return min((s.average_risk for s in summaries), default=0.0)


def rank_routes(summaries: list[RouteRiskSummary]) -> list[RouteRiskSummary]:
    """Best route first. Sorting is stable, so exact ties keep the provider's order."""
    anchor = average_anchor(summaries)
    return sorted(summaries, key=lambda s: s.sort_key(anchor))


def deciding_criterion(
    winner: RouteRiskSummary, other: RouteRiskSummary, avg_anchor: float | None = None
) -> Criterion | None:
    """The first criterion in preference order on which `winner` beats `other`."""
    anchor = average_anchor([winner, other]) if avg_anchor is None else avg_anchor
    for criterion, a, b in zip(CRITERIA, winner.sort_key(anchor), other.sort_key(anchor)):
        if a != b:
            return criterion
    return None
