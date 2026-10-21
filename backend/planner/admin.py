from django.contrib import admin

from .models import TripPlan


@admin.register(TripPlan)
class TripPlanAdmin(admin.ModelAdmin):
    list_display = (
        "origin_label",
        "destination_label",
        "departure_time",
        "load_weight_lbs",
        "weather_source",
        "created_at",
    )
    list_filter = ("weather_source", "include_hos")
    search_fields = ("origin_label", "destination_label")
    readonly_fields = ("id", "created_at")
