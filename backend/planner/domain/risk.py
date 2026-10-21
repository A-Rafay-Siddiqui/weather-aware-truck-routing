"""Weather risk classification for a single checkpoint.

Implements the assessment's threshold table and load rules exactly. Everything here is
pure (no I/O) so it can be unit-tested exhaustively and reused by the route ranker and
the heatmap builder.

Boundary convention: the spec's ranges share their endpoints (e.g. rain "0.10–0.25" and
"0.25–0.50"). We treat each lower bound as inclusive, so a value on a boundary falls into
the *more severe* level, which is the conservative choice for a safety tool. Where the
spec states an explicit operator we follow it literally: wind "≥55" is No Travel, while
rain ">1.00" and snow ">3.0" mean exactly 1.00 in/hr rain is still Severe.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum


class RiskLevel(IntEnum):
    """Ordered risk levels. The integer value doubles as the numeric risk score (0–4)."""

    LOW = 0
    MODERATE = 1
    HIGH = 2
    SEVERE = 3
    NO_TRAVEL = 4

    @property
    def key(self) -> str:
        return self.name.lower()

    @property
    def label(self) -> str:
        return self.name.replace("_", " ").title()


@dataclass(frozen=True)
class Threshold:
    level: RiskLevel
    minimum: float
    inclusive: bool = True

    def matches(self, value: float) -> bool:
        return value >= self.minimum if self.inclusive else value > self.minimum


# Checked from most to least severe; the first match wins, otherwise LOW.
WIND_THRESHOLDS_MPH = (
    Threshold(RiskLevel.NO_TRAVEL, 55),
    Threshold(RiskLevel.SEVERE, 45),
    Threshold(RiskLevel.HIGH, 35),
    Threshold(RiskLevel.MODERATE, 25),
)
RAIN_THRESHOLDS_IN_HR = (
    Threshold(RiskLevel.NO_TRAVEL, 1.00, inclusive=False),
    Threshold(RiskLevel.SEVERE, 0.50),
    Threshold(RiskLevel.HIGH, 0.25),
    Threshold(RiskLevel.MODERATE, 0.10),
)
SNOW_THRESHOLDS_IN_HR = (
    Threshold(RiskLevel.NO_TRAVEL, 3.0, inclusive=False),
    Threshold(RiskLevel.SEVERE, 2.0),
    Threshold(RiskLevel.HIGH, 1.0),
    Threshold(RiskLevel.MODERATE, 0.5),
)


@dataclass(frozen=True)
class LoadRule:
    """Escalates the wind risk when a heavy load meets strong wind."""

    min_wind_mph: float
    max_wind_mph: float  # exclusive
    min_load_lbs: float  # exclusive (spec says "> N lb")
    level: RiskLevel

    def applies(self, wind_mph: float, load_lbs: float) -> bool:
        return self.min_wind_mph <= wind_mph < self.max_wind_mph and load_lbs > self.min_load_lbs

    def describe(self) -> str:
        return (
            f"{self.min_wind_mph:g}–{self.max_wind_mph - 1:g} mph wind with load over "
            f"{self.min_load_lbs:,.0f} lb → {self.level.label}"
        )


# "≥55 mph → No Travel for any load" is already covered by WIND_THRESHOLDS_MPH.
LOAD_RULES = (
    LoadRule(45, 55, 30_000, RiskLevel.NO_TRAVEL),
    LoadRule(35, 45, 40_000, RiskLevel.SEVERE),
)


def _classify(value: float, thresholds: tuple[Threshold, ...]) -> RiskLevel:
    for threshold in thresholds:
        if threshold.matches(value):
            return threshold.level
    return RiskLevel.LOW


def classify_wind(mph: float) -> RiskLevel:
    return _classify(mph, WIND_THRESHOLDS_MPH)


def classify_rain(in_per_hr: float) -> RiskLevel:
    return _classify(in_per_hr, RAIN_THRESHOLDS_IN_HR)


def classify_snow(in_per_hr: float) -> RiskLevel:
    return _classify(in_per_hr, SNOW_THRESHOLDS_IN_HR)


@dataclass(frozen=True)
class Conditions:
    """Weather at one place and time, in the units the risk table uses."""

    wind_mph: float
    rain_in_hr: float
    snow_in_hr: float
    gust_mph: float | None = None
    weather_code: int | None = None


@dataclass(frozen=True)
class RiskAssessment:
    level: RiskLevel
    wind: RiskLevel
    rain: RiskLevel
    snow: RiskLevel
    load_rule: LoadRule | None = None
    factors: tuple[str, ...] = field(default_factory=tuple)

    @property
    def score(self) -> int:
        return int(self.level)


def assess(conditions: Conditions, load_lbs: float) -> RiskAssessment:
    """Classify a checkpoint. The overall level is the worst of wind (after load rules), rain and snow."""
    wind = classify_wind(conditions.wind_mph)
    rain = classify_rain(conditions.rain_in_hr)
    snow = classify_snow(conditions.snow_in_hr)

    applied_rule = None
    for rule in LOAD_RULES:
        if rule.applies(conditions.wind_mph, load_lbs) and rule.level > wind:
            wind, applied_rule = rule.level, rule
            break

    level = max(wind, rain, snow)
    factors: list[str] = []
    if wind > RiskLevel.LOW:
        factors.append(f"Wind {conditions.wind_mph:.0f} mph → {classify_wind(conditions.wind_mph).label}")
    if applied_rule:
        factors.append(f"Load rule: {applied_rule.describe()}")
    if rain > RiskLevel.LOW:
        factors.append(f"Rain {conditions.rain_in_hr:.2f} in/hr → {rain.label}")
    if snow > RiskLevel.LOW:
        factors.append(f"Snow {conditions.snow_in_hr:.2f} in/hr → {snow.label}")

    return RiskAssessment(level=level, wind=wind, rain=rain, snow=snow, load_rule=applied_rule, factors=tuple(factors))


def rules_as_dict() -> dict:
    """Serializable description of the rules, so the UI legend never drifts from the backend."""

    def rows(thresholds: tuple[Threshold, ...]) -> list[dict]:
        return [{"level": t.level.key, "min": t.minimum, "inclusive": t.inclusive} for t in thresholds]

    return {
        "levels": [{"key": lvl.key, "label": lvl.label, "score": int(lvl)} for lvl in RiskLevel],
        "wind_mph": rows(WIND_THRESHOLDS_MPH),
        "rain_in_hr": rows(RAIN_THRESHOLDS_IN_HR),
        "snow_in_hr": rows(SNOW_THRESHOLDS_IN_HR),
        "load_rules": [
            {
                "min_wind_mph": r.min_wind_mph,
                "max_wind_mph": r.max_wind_mph,
                "min_load_lbs": r.min_load_lbs,
                "level": r.level.key,
                "description": r.describe(),
            }
            for r in LOAD_RULES
        ],
    }
