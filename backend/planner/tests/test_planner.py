from datetime import datetime, timedelta, timezone

import pytest

from planner.services.heatmap import MAX_CELLS, build_heatmap, inv_merc_y, merc_y
from planner.services.planner import PlanRequest, build_plan, format_duration

from .fakes import DESTINATION, ORIGIN, CalmWeather, FakeRouting

DEPARTURE = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(hours=3)


def request(**kw):
    defaults = dict(
        origin=ORIGIN,
        destination=DESTINATION,
        departure=DEPARTURE,
        load_lbs=35_000,
        interval_miles=25,
        weather_source="live",
        include_hos=True,
    )
    return PlanRequest(**{**defaults, **kw})


class TestBuildPlan:
    def test_calm_weather_recommends_fastest_route(self):
        plan = build_plan(request(), FakeRouting(), CalmWeather())
        assert [r["id"] for r in plan["routes"]] == ["A", "B", "C"]
        assert plan["recommended_route_id"] == "A"
        assert "faster" in plan["recommendation"]["reasons"][0]
        assert plan["recommendation"]["warnings"] == []
        for route in plan["routes"]:
            assert route["risk"]["max_level"] == "low"
            assert route["risk"]["miles_by_level"]["low"] == pytest.approx(route["distance_miles"], abs=0.2)

    @pytest.mark.parametrize("interval", [10, 25, 50])
    def test_checkpoint_spacing_and_etas(self, interval):
        plan = build_plan(request(interval_miles=interval), FakeRouting(), CalmWeather())
        cps = plan["routes"][0]["checkpoints"]
        miles = [c["mile"] for c in cps]
        assert miles[0] == 0
        assert all(b - a == pytest.approx(interval, abs=0.15) for a, b in zip(miles[:-2], miles[1:-1]))
        etas = [datetime.fromisoformat(c["eta"]) for c in cps]
        assert etas[0] == DEPARTURE
        assert etas == sorted(etas)
        # 62 mph route: ETA at mile m ≈ m / 62 hours (< 8h, so no HOS stop yet).
        assert (etas[1] - DEPARTURE).total_seconds() == pytest.approx(miles[1] / 62 * 3600, rel=0.01)

    def test_weather_is_sampled_at_each_checkpoint_eta_window(self):
        weather = CalmWeather()
        build_plan(request(), FakeRouting(), weather)
        n_locations, start, end = weather.requested[0]
        assert start <= DEPARTURE and end > DEPARTURE + timedelta(hours=5)

    def test_load_rule_changes_the_outcome(self):
        windy = CalmWeather(wind=47)
        light = build_plan(request(load_lbs=20_000), FakeRouting(), windy)
        heavy = build_plan(request(load_lbs=36_000), FakeRouting(), windy)
        assert light["routes"][0]["risk"]["max_level"] == "severe"
        assert heavy["routes"][0]["risk"]["max_level"] == "no_travel"
        assert heavy["recommendation"]["warnings"]  # every route is No Travel
        assert any(c["risk"]["load_rule_applied"] for c in heavy["routes"][0]["checkpoints"])

    def test_simulated_storm_steers_recommendation_away_from_fastest_route(self):
        plan = build_plan(request(weather_source="simulated", load_lbs=42_000), FakeRouting(), CalmWeather())
        by_id = {r["id"]: r for r in plan["routes"]}
        assert plan["simulation"]["storms"]
        assert by_id["A"]["risk"]["max_level"] in ("severe", "no_travel")
        assert plan["recommended_route_id"] != "A"
        assert plan["recommendation"]["reasons"]

    def test_display_path_is_time_annotated_and_monotonic(self):
        plan = build_plan(request(), FakeRouting(), CalmWeather())
        path = plan["routes"][0]["path"]
        times = [p[2] for p in path]
        assert times[0] == 0 and times == sorted(times)
        assert times[-1] == plan["routes"][0]["travel_time_s"]

    def test_hos_stops_on_long_routes(self):
        slow = FakeRouting()
        plan = build_plan(request(), slow, CalmWeather())
        route = plan["routes"][2]  # ~370 mi at 55 mph ≈ 6.7h: no stops
        assert route["stops"] == []
        assert route["travel_time_s"] == route["drive_time_s"]

    def test_hos_toggle_off(self):
        plan = build_plan(request(include_hos=False), FakeRouting(), CalmWeather())
        assert all(r["travel_time_s"] == r["drive_time_s"] for r in plan["routes"])


class TestHeatmap:
    def test_grid_fits_budget_and_covers_routes(self):
        plan = build_plan(request(), FakeRouting(), CalmWeather(wind=30))
        paths = [[(p[1], p[0]) for p in r["path"]] for r in plan["routes"]]
        hm = build_heatmap(paths, DEPARTURE, 35_000, CalmWeather(wind=30))
        assert 0 < len(hm["cells"]) <= MAX_CELLS
        assert hm["hours"] == 49
        assert len(hm["risk"][0]) == 49 and hm["risk"][0][0] == 1  # 30 mph → Moderate
        assert hm["west"] < ORIGIN.lon and hm["east"] > ORIGIN.lon
        assert hm["south"] < DESTINATION.lat < hm["north"]
        assert all(0 <= x < hm["cols"] and 0 <= y < hm["rows"] for x, y in hm["cells"])
        assert datetime.fromisoformat(hm["start_time"]) >= DEPARTURE

    def test_mercator_roundtrip(self):
        for lat in (-60, 0, 25.5, 48.9):
            assert inv_merc_y(merc_y(lat)) == pytest.approx(lat)


def test_format_duration():
    assert format_duration(59 * 60) == "59m"
    assert format_duration(3600 * 11 + 60 * 5) == "11h 05m"
