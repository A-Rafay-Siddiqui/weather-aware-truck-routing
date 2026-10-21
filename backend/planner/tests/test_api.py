from datetime import timedelta

import pytest
from django.core.cache import cache
from django.utils import timezone
from rest_framework.test import APIClient

from planner.models import TripPlan
from planner.providers.base import NoRouteFound, Place
from planner.services import providers

from .fakes import CalmWeather, FakeRouting

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def fake_providers(monkeypatch):
    cache.clear()  # throttles live in the cache
    monkeypatch.setattr(providers, "routing_provider", FakeRouting)
    monkeypatch.setattr(providers, "live_weather", CalmWeather)


@pytest.fixture
def client():
    return APIClient()


def payload(**kw):
    body = {
        "origin": {"label": "Chicago, IL", "lat": 41.8781, "lon": -87.6298},
        "destination": {"label": "Des Moines, IA", "lat": 41.5868, "lon": -93.625},
        "departure_time": (timezone.now() + timedelta(hours=1)).isoformat(),
        "load_weight_lbs": 30_000,
        "sample_interval_miles": 25,
    }
    return {**body, **kw}


def test_create_fetch_and_heatmap(client):
    res = client.post("/api/v1/trip-plans/", payload(), format="json")
    assert res.status_code == 201, res.data
    body = res.json()
    assert body["recommended_route_id"] in {"A", "B", "C"}
    assert len(body["routes"]) == 3
    plan_id = body["id"]

    assert client.get(f"/api/v1/trip-plans/{plan_id}/").json()["routes"][0]["checkpoints"]
    hm = client.get(f"/api/v1/trip-plans/{plan_id}/heatmap/")
    assert hm.status_code == 200 and hm.json()["hours"] == 49
    assert TripPlan.objects.get(pk=plan_id).heatmap is not None  # cached on the row
    assert client.get("/api/v1/trip-plans/").json()[0]["id"] == plan_id


@pytest.mark.parametrize(
    "override, field",
    [
        ({"sample_interval_miles": 30}, "sample_interval_miles"),
        ({"load_weight_lbs": -1}, "load_weight_lbs"),
        ({"departure_time": "2001-01-01T00:00:00Z"}, "departure_time"),
        ({"destination": {"label": "Same", "lat": 41.8781, "lon": -87.6298}}, "non_field_errors"),
    ],
)
def test_validation(client, override, field):
    res = client.post("/api/v1/trip-plans/", payload(**override), format="json")
    assert res.status_code == 400
    assert field in res.json()


def test_provider_errors_become_clean_responses(client, monkeypatch):
    class NoRoutes:
        def routes(self, *args):
            raise NoRouteFound()

    monkeypatch.setattr(providers, "routing_provider", NoRoutes)
    res = client.post("/api/v1/trip-plans/", payload(), format="json")
    assert res.status_code == 422
    assert "No truck route" in res.json()["detail"]


def test_geocode(client, monkeypatch):
    class Geo:
        def search(self, q):
            return [Place("Dallas, TX", 32.7, -96.8)]

    monkeypatch.setattr(providers, "geocoder", Geo)
    assert client.get("/api/v1/geocode/?q=dal").json()["results"][0]["label"] == "Dallas, TX"


def test_health_and_rules(client):
    assert client.get("/api/v1/health/").json()["status"] == "ok"
    assert len(client.get("/api/v1/risk-rules/").json()["wind_mph"]) == 4
