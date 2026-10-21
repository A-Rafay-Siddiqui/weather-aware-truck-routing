"""Builds providers from settings. Tests patch these functions to inject fakes."""

from __future__ import annotations

from django.conf import settings

from ..providers.openmeteo import OpenMeteoWeather
from ..providers.synthetic import SyntheticWeather
from ..providers.tomtom import TomTomClient, TomTomGeocoder, TomTomRouting


def routing_provider() -> TomTomRouting:
    return TomTomRouting(TomTomClient(settings.TOMTOM_API_KEY))


def geocoder() -> TomTomGeocoder:
    return TomTomGeocoder(TomTomClient(settings.TOMTOM_API_KEY))


def live_weather() -> OpenMeteoWeather:
    return OpenMeteoWeather(base_url=settings.OPEN_METEO_URL, api_key=settings.OPEN_METEO_API_KEY)


def weather_for_plan(result: dict):
    """The same weather source a stored plan was built with (needed for its heatmap)."""
    if result.get("simulation"):
        return SyntheticWeather.from_dict(result["simulation"])
    return live_weather()
