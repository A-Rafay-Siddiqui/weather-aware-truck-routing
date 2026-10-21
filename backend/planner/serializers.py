from datetime import timedelta

from django.utils import timezone
from rest_framework import serializers

from .models import TripPlan

MAX_DEPARTURE_DAYS_AHEAD = 7  # forecasts get unreliable beyond this; Open-Meteo also caps at 16 days
MAX_LOAD_LBS = 120_000


class PlaceSerializer(serializers.Serializer):
    label = serializers.CharField(max_length=255)
    lat = serializers.FloatField(min_value=-90, max_value=90)
    lon = serializers.FloatField(min_value=-180, max_value=180)


class PlanRequestSerializer(serializers.Serializer):
    origin = PlaceSerializer()
    destination = PlaceSerializer()
    departure_time = serializers.DateTimeField()
    load_weight_lbs = serializers.IntegerField(min_value=0, max_value=MAX_LOAD_LBS)
    sample_interval_miles = serializers.ChoiceField(choices=[10, 25, 50])
    weather_source = serializers.ChoiceField(choices=[c for c, _ in TripPlan.WEATHER_CHOICES], default="live")
    include_hos = serializers.BooleanField(default=True)

    def validate_departure_time(self, value):
        now = timezone.now()
        if value < now - timedelta(minutes=15):
            raise serializers.ValidationError("Departure time can't be in the past.")
        if value > now + timedelta(days=MAX_DEPARTURE_DAYS_AHEAD):
            raise serializers.ValidationError(
                f"Departure must be within {MAX_DEPARTURE_DAYS_AHEAD} days; forecasts don't reach further."
            )
        # Leaving "a few minutes ago" means leaving now.
        return max(value, now)

    def validate(self, attrs):
        o, d = attrs["origin"], attrs["destination"]
        if abs(o["lat"] - d["lat"]) < 1e-4 and abs(o["lon"] - d["lon"]) < 1e-4:
            raise serializers.ValidationError("Origin and destination must be different places.")
        return attrs


class TripPlanSerializer(serializers.ModelSerializer):
    """The stored plan: id + metadata merged with the computed result document."""

    class Meta:
        model = TripPlan
        fields = ["id", "created_at"]

    def to_representation(self, instance):
        data = super().to_representation(instance)
        return {**data, **instance.result}


class TripPlanListSerializer(serializers.ModelSerializer):
    origin = serializers.CharField(source="origin_label")
    destination = serializers.CharField(source="destination_label")

    class Meta:
        model = TripPlan
        fields = ["id", "created_at", "origin", "destination", "departure_time", "weather_source"]
