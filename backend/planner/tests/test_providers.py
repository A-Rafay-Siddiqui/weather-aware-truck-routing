from datetime import datetime, timedelta, timezone

import httpx
import pytest

from planner.providers.base import NoRouteFound, ProviderError
from planner.providers.openmeteo import OpenMeteoWeather, parse_series
from planner.providers.synthetic import Storm, SyntheticWeather
from planner.providers.tomtom import TomTomClient, TomTomGeocoder, TomTomRouting, parse_route

from .fakes import DESTINATION, ORIGIN, _path


def tomtom_route(via_lat: float, seconds: float = 20_000):
    pts = _path(via_lat)
    return {
        "summary": {"lengthInMeters": 530_000, "travelTimeInSeconds": seconds, "trafficDelayInSeconds": 120},
        "legs": [{"points": [{"latitude": a, "longitude": b} for a, b in pts]}],
        "progress": [
            {"pointIndex": 0, "travelTimeInSeconds": 0, "distanceInMeters": 0},
            {"pointIndex": len(pts) - 1, "travelTimeInSeconds": seconds, "distanceInMeters": 530_000},
        ],
        "sections": [
            {
                "sectionType": "IMPORTANT_ROAD_STRETCH",
                "startPointIndex": 0,
                "endPointIndex": 30,
                "roadNumbers": [{"text": "I-88"}],
            },
            {
                "sectionType": "IMPORTANT_ROAD_STRETCH",
                "startPointIndex": 30,
                "endPointIndex": 240,
                "roadNumbers": [{"text": "I-80"}, {"text": "US-6"}],
            },
            {"sectionType": "TRAVEL_MODE", "startPointIndex": 0, "endPointIndex": 240},
        ],
    }


def mock_client(handler) -> TomTomClient:
    return TomTomClient(
        "test-key", client=httpx.Client(base_url="https://api.tomtom.com", transport=httpx.MockTransport(handler))
    )


class TestTomTomRouting:
    def test_parse_route(self):
        option = parse_route(tomtom_route(41.7))
        assert option.length_m == 530_000
        assert option.progress[-1] == (240, 20_000)
        assert option.road_numbers == ["I-80", "I-88"]  # ordered by miles carried

    def test_truck_parameters_are_sent(self):
        seen = {}

        def handler(request: httpx.Request):
            seen.update({k: request.url.params.get_list(k) for k in request.url.params})
            return httpx.Response(200, json={"routes": [tomtom_route(41.7), tomtom_route(43), tomtom_route(40.5)]})

        routes = TomTomRouting(mock_client(handler)).routes(
            ORIGIN, DESTINATION, datetime.now(timezone.utc) + timedelta(hours=2), 40_000
        )
        assert len(routes) == 3
        assert seen["travelMode"] == ["truck"]
        assert seen["vehicleWeight"] == [str(round(75_000 * 0.45359237))]  # cargo + tractor-trailer tare
        assert seen["maxAlternatives"] == ["2"]
        assert seen["extendedRouteRepresentation"] == ["distance", "travelTime"]
        assert seen["departAt"][0].endswith("+00:00")

    def test_falls_back_to_other_strategies_when_alternatives_are_missing(self):
        def handler(request: httpx.Request):
            params = request.url.params
            if params.get("maxAlternatives"):
                return httpx.Response(200, json={"routes": [tomtom_route(41.7)]})
            if params.get("avoid") == "tollRoads":
                return httpx.Response(200, json={"routes": [tomtom_route(41.7001)]})  # duplicate → dropped
            if params.get("routeType") == "eco":
                return httpx.Response(200, json={"routes": [tomtom_route(43.2)]})
            return httpx.Response(200, json={"routes": [tomtom_route(40.2)]})

        routes = TomTomRouting(mock_client(handler)).routes(ORIGIN, DESTINATION, datetime.now(timezone.utc), 10_000)
        assert [r.strategy for r in routes] == ["fastest", "eco", "short"]

    def test_no_route_error(self):
        def handler(request):
            return httpx.Response(
                400, json={"error": {"description": "Engine error while executing route request: NO_ROUTE_FOUND"}}
            )

        with pytest.raises(NoRouteFound):
            TomTomRouting(mock_client(handler)).routes(ORIGIN, DESTINATION, datetime.now(timezone.utc), 0)

    def test_missing_key(self):
        with pytest.raises(ProviderError) as exc:
            TomTomClient("")
        assert exc.value.status_code == 503


class TestGeocoder:
    def test_search_labels_and_cache(self):
        calls = []

        def handler(request):
            calls.append(request.url)
            return httpx.Response(
                200,
                json={
                    "results": [
                        {
                            "type": "Geography",
                            "address": {"freeformAddress": "Dallas, TX"},
                            "position": {"lat": 32.7, "lon": -96.8},
                        },
                        {
                            "type": "POI",
                            "poi": {"name": "Pilot Travel Center"},
                            "address": {"freeformAddress": "Dallas, TX"},
                            "position": {"lat": 32.8, "lon": -96.7},
                        },
                    ]
                },
            )

        geocoder = TomTomGeocoder(mock_client(handler))
        places = geocoder.search("Dallas")
        assert [p.label for p in places] == ["Dallas, TX", "Pilot Travel Center, Dallas, TX"]
        geocoder.search("dallas ")
        assert len(calls) == 1  # second lookup served from cache


class TestOpenMeteo:
    def test_parse_series_sums_rain_and_showers(self):
        item = {
            "hourly": {
                "time": [0, 3600],
                "wind_speed_10m": [10, 20],
                "wind_gusts_10m": [15, 30],
                "rain": [0.1, None],
                "showers": [0.05, 0.2],
                "snowfall": [0, 0.4],
                "weather_code": [61, 71],
            }
        }
        s = parse_series((1.0, 2.0), item)
        assert s.rain_in == pytest.approx([0.15, 0.2])
        assert s.snow_in == [0, 0.4]

    def test_batches_dedupes_and_caches(self, monkeypatch):
        requests = []

        def handler(request: httpx.Request):
            lats = request.url.params["latitude"].split(",")
            requests.append(len(lats))
            return httpx.Response(
                200,
                json=[
                    {
                        "hourly": {
                            "time": [0],
                            "wind_speed_10m": [5],
                            "wind_gusts_10m": [6],
                            "rain": [0],
                            "showers": [0],
                            "snowfall": [0],
                            "weather_code": [0],
                        }
                    }
                    for _ in lats
                ],
            )

        real_client = httpx.Client
        monkeypatch.setattr(httpx, "Client", lambda **kw: real_client(transport=httpx.MockTransport(handler), **kw))
        provider = OpenMeteoWeather(batch_size=2)
        start = datetime(2030, 1, 1, tzinfo=timezone.utc)
        locs = [(40.001, -100.001), (40.0, -100.0), (41, -101), (42, -102)]  # first two round to the same cell
        out = provider.series(locs, start, start + timedelta(hours=1))
        assert len(out) == 4 and out[0] is out[1]
        assert sorted(requests) == [1, 2]
        provider.series(locs, start, start + timedelta(hours=1))
        assert len(requests) == 2  # all cached


class TestSyntheticWeather:
    def test_storm_peaks_at_its_center_and_time(self):
        t = datetime(2030, 1, 1, 12, tzinfo=timezone.utc)
        weather = SyntheticWeather(storms=(Storm(lat=40, lon=-100, peak_time=t.timestamp()),))
        center, far = weather.series([(40, -100), (45, -90)], t - timedelta(hours=1), t + timedelta(hours=1))
        peak = center.at(t.timestamp())
        assert peak.wind_mph == pytest.approx(62, abs=0.5)
        assert far.at(t.timestamp()).wind_mph == pytest.approx(8, abs=0.5)
        assert SyntheticWeather.from_dict(weather.to_dict()) == weather


class TestOpenMeteoBudget:
    def test_forecast_window_uses_fixed_horizons(self):
        from planner.providers.openmeteo import forecast_window

        now = datetime(2030, 1, 1, 10, 42, tzinfo=timezone.utc)
        start, end = forecast_window(now + timedelta(hours=30), now=now)
        assert start == datetime(2030, 1, 1, 10, tzinfo=timezone.utc)
        assert end - start == timedelta(hours=72)
        assert forecast_window(now + timedelta(days=5), now=now)[1] - start == timedelta(hours=168)

    def test_snap_shares_nearby_points(self):
        from planner.providers.openmeteo import snap

        assert snap((40.012, -100.024)) == snap((39.99, -99.99)) == (40.0, -100.0)
        assert snap((40.03, -100.0)) == (40.05, -100.0)

    def test_budget_waits_for_next_minute_instead_of_failing(self):
        from planner.providers.openmeteo import MinuteBudget

        clock = {"t": 120.0}
        slept = []

        def sleep(s):
            slept.append(s)
            clock["t"] += s

        budget = MinuteBudget(limit=150, clock=lambda: clock["t"], sleep=sleep)
        budget.acquire(100, deadline=1e9)
        budget.acquire(100, deadline=1e9)  # would make 200 > 150 → waits for the next minute
        assert len(slept) == 1 and 60 <= slept[0] <= 61

    def test_budget_gives_up_past_deadline(self):
        from planner.providers.openmeteo import MinuteBudget

        budget = MinuteBudget(limit=50, clock=lambda: 130.0, sleep=lambda s: None)
        budget.acquire(50, deadline=1e9)
        with pytest.raises(ProviderError) as exc:
            budget.acquire(10, deadline=140.0)
        assert exc.value.status_code == 429

    def test_429_is_retried_once_after_waiting(self, monkeypatch):
        from planner.providers.openmeteo import MinuteBudget

        calls = []

        def handler(request: httpx.Request):
            calls.append(1)
            if len(calls) == 1:
                return httpx.Response(429, json={"reason": "Minutely API request limit exceeded"})
            return httpx.Response(
                200,
                json=[
                    {
                        "hourly": {
                            "time": [0],
                            "wind_speed_10m": [5],
                            "wind_gusts_10m": [6],
                            "rain": [0],
                            "showers": [0],
                            "snowfall": [0],
                            "weather_code": [0],
                        }
                    }
                ],
            )

        real_client = httpx.Client
        monkeypatch.setattr(httpx, "Client", lambda **kw: real_client(transport=httpx.MockTransport(handler), **kw))
        slept = []
        provider = OpenMeteoWeather(budget=MinuteBudget(500, sleep=slept.append))
        start = datetime.now(timezone.utc)
        assert len(provider.series([(40, -100)], start, start + timedelta(hours=2))) == 1
        assert len(calls) == 2 and len(slept) == 1


class TestRouteCache:
    def test_identical_requests_reuse_routes(self):
        calls = []

        def handler(request):
            calls.append(1)
            return httpx.Response(200, json={"routes": [tomtom_route(41.7), tomtom_route(43), tomtom_route(40.5)]})

        routing = TomTomRouting(mock_client(handler))
        dep = datetime.now(timezone.utc) + timedelta(hours=3)
        routing.routes(ORIGIN, DESTINATION, dep, 40_000)
        routing.routes(ORIGIN, DESTINATION, dep, 40_200)  # same 1,000 lb bucket
        assert len(calls) == 1
        routing.routes(ORIGIN, DESTINATION, dep, 20_000)
        assert len(calls) == 2
