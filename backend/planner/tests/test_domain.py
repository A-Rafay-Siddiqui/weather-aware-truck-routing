import math

import pytest

from planner.domain.geometry import (
    cell_signature,
    cumulative_miles,
    haversine_miles,
    overlap_ratio,
    point_at_distance,
    sample_checkpoints,
    simplify_indices,
)
from planner.domain.ranking import RouteRiskSummary, deciding_criterion, rank_routes
from planner.domain.risk import RiskLevel
from planner.domain.timing import HOUR, HosPolicy, NoStops, RouteTiming
from planner.domain.weather import WeatherSeries


def straight_line(miles: float, n: int = 200):
    """A due-north line from (35, -100) of roughly `miles` length."""
    dlat = miles / 69.09
    return [(35 + dlat * i / (n - 1), -100.0) for i in range(n)]


class TestGeometry:
    def test_haversine_known_distance(self):
        # Chicago → Denver ≈ 920 mi great-circle
        assert haversine_miles((41.8781, -87.6298), (39.7392, -104.9903)) == pytest.approx(920, rel=0.01)

    @pytest.mark.parametrize("interval", [10, 25, 50])
    def test_checkpoints_every_interval_and_segments_tile_the_route(self, interval):
        pts = straight_line(237)
        cum = cumulative_miles(pts)
        samples = sample_checkpoints(pts, cum, interval)
        miles = [s.mile for s in samples]
        assert miles[0] == 0 and miles[-1] == pytest.approx(cum[-1])
        assert all(b - a == pytest.approx(interval) for a, b in zip(miles[:-2], miles[1:-1]))
        # Segments are contiguous and cover exactly the full length.
        assert samples[0].segment_start_mile == 0
        assert samples[-1].segment_end_mile == pytest.approx(cum[-1])
        for a, b in zip(samples, samples[1:]):
            assert a.segment_end_mile == pytest.approx(b.segment_start_mile)
        assert sum(s.segment_miles for s in samples) == pytest.approx(cum[-1])

    def test_last_mark_too_close_to_destination_is_dropped(self):
        pts = straight_line(50.5)
        cum = cumulative_miles(pts)
        miles = [s.mile for s in sample_checkpoints(pts, cum, 25)]
        assert len(miles) == 3  # 0, 25, end (≈50.5) — no extra point at 50

    def test_point_at_distance_interpolates(self):
        pts = [(0.0, 0.0), (1.0, 0.0)]
        cum = cumulative_miles(pts)
        lat, lon = point_at_distance(pts, cum, cum[-1] / 4)
        assert lat == pytest.approx(0.25) and lon == 0

    def test_simplify_keeps_corners_and_drops_collinear_points(self):
        line = [(0, i * 0.01) for i in range(50)] + [(i * 0.01, 0.49) for i in range(1, 50)]
        keep = simplify_indices(line, 0.0001)
        assert keep == [0, 49, len(line) - 1]

    def test_overlap_detects_duplicate_routes(self):
        a = straight_line(100)
        b = [(lat, lon + 1e-4) for lat, lon in a]
        c = [(lat, lon + 1.0) for lat, lon in a]
        assert overlap_ratio(cell_signature(a), cell_signature(b)) > 0.9
        assert overlap_ratio(cell_signature(a), cell_signature(c)) == 0


class TestTiming:
    def test_route_timing_interpolates_both_ways(self):
        t = RouteTiming([0, 100, 200], [0, 3600, 9000])
        assert t.drive_time_at(50) == 1800
        assert t.drive_time_at(150) == 6300
        assert t.mile_at(6300) == pytest.approx(150)

    @pytest.mark.parametrize(
        "drive_h, wall_h",
        [
            (0, 0),
            (7.5, 7.5),
            (8, 8),  # arriving exactly at the 8h mark: break not needed
            (9, 9.5),  # 30-min break taken at 8h
            (11, 11.5),
            (12, 22.5),  # 11h block + 0.5 break + 10h rest, then 1h
            (20, 31.0),  # second block: break at 19h of driving
            (23, 44.0),  # two full blocks (each +10h rest +0.5h break), then 1h into the third
        ],
    )
    def test_hos_wall_clock(self, drive_h, wall_h):
        assert HosPolicy().wall_seconds(drive_h * HOUR) == pytest.approx(wall_h * HOUR)

    def test_hos_stops_match_wall_clock(self):
        hos = HosPolicy()
        stops = hos.stops_before(23 * HOUR)
        assert [(s.kind, s.drive_seconds / HOUR) for s in stops] == [
            ("break", 8),
            ("rest", 11),
            ("break", 19),
            ("rest", 22),
        ]
        # Wall time = driving + every stop's duration.
        assert hos.wall_seconds(23 * HOUR) == 23 * HOUR + sum(s.duration_seconds for s in stops)

    def test_hos_is_monotonic(self):
        hos = HosPolicy()
        walls = [hos.wall_seconds(m * 60) for m in range(0, 40 * 60, 7)]
        assert all(b >= a for a, b in zip(walls, walls[1:]))

    def test_no_stops_policy(self):
        assert NoStops().wall_seconds(30 * HOUR) == 30 * HOUR
        assert NoStops().stops_before(30 * HOUR) == []


class TestWeatherSeries:
    series = WeatherSeries(
        lat=0,
        lon=0,
        times=[0, 3600, 7200],
        wind_mph=[10, 30, 50],
        gust_mph=[15, 40, 60],
        rain_in=[0.0, 0.2, 0.6],
        snow_in=[0, 0, 0],
        weather_code=[0, 61, 63],
    )

    def test_wind_is_interpolated(self):
        assert self.series.at(1800).wind_mph == pytest.approx(20)

    def test_precip_uses_the_hour_window_containing_t(self):
        # 00:30 falls in the 00:00–01:00 window, which Open-Meteo stamps at 01:00.
        assert self.series.at(1800).rain_in_hr == 0.2
        assert self.series.at(3600).rain_in_hr == 0.2
        assert self.series.at(3601).rain_in_hr == 0.6

    def test_clamps_outside_range(self):
        assert self.series.at(-100).wind_mph == 10
        assert self.series.at(99999).rain_in_hr == 0.6


def summary(route_id, travel_h=10, **miles):
    levels = {
        "low": RiskLevel.LOW,
        "moderate": RiskLevel.MODERATE,
        "high": RiskLevel.HIGH,
        "severe": RiskLevel.SEVERE,
        "no_travel": RiskLevel.NO_TRAVEL,
    }
    segments = [(m, levels[k]) for k, m in miles.items()]
    return RouteRiskSummary.from_segments(route_id, segments, travel_h * HOUR)


class TestRanking:
    def test_fewest_severe_miles_wins_over_travel_time(self):
        a = summary("A", travel_h=8, low=400, severe=20)
        b = summary("B", travel_h=12, low=420, high=50)
        assert [s.route_id for s in rank_routes([a, b])] == ["B", "A"]
        assert deciding_criterion(b, a).key == "severe_miles"

    def test_high_miles_break_severe_tie(self):
        a = summary("A", low=400, high=30)
        b = summary("B", low=400, high=10, moderate=20)
        assert rank_routes([a, b])[0].route_id == "B"
        assert deciding_criterion(b, a).key == "high_miles"

    def test_average_risk_then_time(self):
        a = summary("A", travel_h=9, low=300, moderate=100)  # avg 0.25
        b = summary("B", travel_h=11, low=400)  # avg 0.0
        assert rank_routes([a, b])[0].route_id == "B"
        assert deciding_criterion(b, a).key == "average_risk"

    def test_negligible_risk_difference_falls_through_to_travel_time(self):
        # avg 0.01 vs 0.0 rounds to the same 0.1 bucket → the 2h-faster route wins.
        a = summary("A", travel_h=9, low=495, moderate=5)
        b = summary("B", travel_h=11, low=500)
        assert rank_routes([a, b])[0].route_id == "A"
        assert deciding_criterion(a, b).key == "travel_time"

    def test_near_equal_averages_tie_instead_of_straddling_a_rounding_boundary(self):
        # 0.33 vs 0.36 would round to different 0.1 buckets; measured from the best they tie.
        a = summary("A", travel_h=11, low=670, moderate=330)  # avg 0.33
        b = summary("B", travel_h=10, low=640, moderate=360)  # avg 0.36, faster
        assert rank_routes([a, b])[0].route_id == "B"
        assert deciding_criterion(b, a).key == "travel_time"

    def test_no_travel_is_worse_than_any_severe(self):
        a = summary("A", low=400, no_travel=5)
        b = summary("B", low=300, severe=100)
        assert rank_routes([a, b])[0].route_id == "B"

    def test_average_is_mile_weighted(self):
        s = summary("A", low=100, high=100)
        assert s.average_risk == pytest.approx(1.0)
        assert s.max_level == RiskLevel.HIGH
        assert math.isclose(s.total_miles, 200)
