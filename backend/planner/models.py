import uuid

from django.db import models


class TripPlan(models.Model):
    """A computed plan, stored as an immutable snapshot.

    The inputs live in typed columns (queryable, validated). The output is one JSON document,
    because it is always read and written whole and its shape belongs to the planner service.
    Normalizing routes and checkpoints into tables would only add joins on every read, and
    nothing needs them yet. Persisting plans gives shareable links (/plans/<id>), and the
    heatmap can be computed lazily and cached on the row.
    """

    WEATHER_LIVE = "live"
    WEATHER_SIMULATED = "simulated"
    WEATHER_CHOICES = [(WEATHER_LIVE, "Live forecast"), (WEATHER_SIMULATED, "Simulated storm")]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    origin_label = models.CharField(max_length=255)
    origin_lat = models.FloatField()
    origin_lon = models.FloatField()
    destination_label = models.CharField(max_length=255)
    destination_lat = models.FloatField()
    destination_lon = models.FloatField()
    departure_time = models.DateTimeField()
    load_weight_lbs = models.PositiveIntegerField()
    sample_interval_miles = models.PositiveSmallIntegerField()
    weather_source = models.CharField(max_length=16, choices=WEATHER_CHOICES, default=WEATHER_LIVE)
    include_hos = models.BooleanField(default=True)

    recommended_route_id = models.CharField(max_length=2)
    result = models.JSONField()
    heatmap = models.JSONField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.origin_label} → {self.destination_label} @ {self.departure_time:%Y-%m-%d %H:%M}"
