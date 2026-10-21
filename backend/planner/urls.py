from django.urls import path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("trip-plans", views.TripPlanViewSet, basename="trip-plan")

urlpatterns = [
    path("health/", views.health, name="health"),
    path("risk-rules/", views.risk_rules, name="risk-rules"),
    path("geocode/", views.GeocodeView.as_view(), name="geocode"),
    *router.urls,
]
