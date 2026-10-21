import pytest

from planner.domain.risk import (
    Conditions,
    RiskLevel,
    assess,
    classify_rain,
    classify_snow,
    classify_wind,
    rules_as_dict,
)

L, M, H, S, N = RiskLevel.LOW, RiskLevel.MODERATE, RiskLevel.HIGH, RiskLevel.SEVERE, RiskLevel.NO_TRAVEL


@pytest.mark.parametrize(
    "mph, level",
    [(0, L), (24.9, L), (25, M), (34, M), (34.9, M), (35, H), (44.9, H), (45, S), (54, S), (54.9, S), (55, N), (80, N)],
)
def test_wind_thresholds(mph, level):
    assert classify_wind(mph) == level


@pytest.mark.parametrize(
    "rate, level",
    [(0, L), (0.099, L), (0.10, M), (0.249, M), (0.25, H), (0.49, H), (0.50, S), (1.00, S), (1.001, N), (2, N)],
)
def test_rain_thresholds(rate, level):
    # Shared boundaries (0.25, 0.50) go to the more severe level; ">1.00" is strict per spec.
    assert classify_rain(rate) == level


@pytest.mark.parametrize(
    "rate, level",
    [(0, L), (0.49, L), (0.5, M), (0.99, M), (1.0, H), (1.99, H), (2.0, S), (3.0, S), (3.01, N)],
)
def test_snow_thresholds(rate, level):
    assert classify_snow(rate) == level


def calm(**kw):
    return Conditions(**{"wind_mph": 5, "rain_in_hr": 0, "snow_in_hr": 0, **kw})


class TestLoadRules:
    def test_55_mph_is_no_travel_for_any_load(self):
        assert assess(calm(wind_mph=55), load_lbs=0).level == N

    @pytest.mark.parametrize("load, level", [(30_000, S), (30_001, N), (45_000, N)])
    def test_45_to_54_mph_with_heavy_load(self, load, level):
        result = assess(calm(wind_mph=50), load_lbs=load)
        assert result.level == level
        assert (result.load_rule is not None) == (level == N)

    @pytest.mark.parametrize("load, level", [(40_000, H), (40_001, S)])
    def test_35_to_44_mph_with_heavy_load(self, load, level):
        assert assess(calm(wind_mph=40), load_lbs=load).level == level

    def test_rule_window_upper_bound_is_exclusive(self):
        # 44.9 mph is still in the 35–44 band → Severe with a heavy load, not the 45–54 rule.
        assert assess(calm(wind_mph=44.9), load_lbs=50_000).level == S
        assert assess(calm(wind_mph=45), load_lbs=50_000).level == N

    def test_load_rules_do_not_touch_light_wind(self):
        assert assess(calm(wind_mph=30), load_lbs=80_000).level == M


class TestCombinedAssessment:
    def test_overall_level_is_worst_factor(self):
        result = assess(calm(wind_mph=26, rain_in_hr=0.6, snow_in_hr=1.2), load_lbs=10_000)
        assert (result.wind, result.rain, result.snow) == (M, S, H)
        assert result.level == S
        assert result.score == 3

    def test_factors_explain_the_level(self):
        result = assess(calm(wind_mph=47, rain_in_hr=0.12), load_lbs=35_000)
        assert result.level == N
        assert any("Load rule" in f for f in result.factors)
        assert any("Rain 0.12" in f for f in result.factors)

    def test_calm_weather_has_no_factors(self):
        result = assess(calm(), load_lbs=20_000)
        assert result.level == L and result.factors == ()


def test_rules_dict_is_complete():
    rules = rules_as_dict()
    assert [lvl["key"] for lvl in rules["levels"]] == ["low", "moderate", "high", "severe", "no_travel"]
    assert len(rules["load_rules"]) == 2
