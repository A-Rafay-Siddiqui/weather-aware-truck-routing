import logging
from datetime import datetime

from django.conf import settings
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action, api_view
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from .domain.risk import rules_as_dict
from .models import TripPlan
from .providers.base import Place, ProviderError
from .serializers import PlanRequestSerializer, TripPlanListSerializer, TripPlanSerializer
from .services import providers
from .services.heatmap import build_heatmap
from .services.planner import PlanRequest, build_plan

logger = logging.getLogger(__name__)


def provider_error_response(exc: ProviderError) -> Response:
    return Response({"detail": exc.message}, status=exc.status_code)


@api_view(["GET"])
def health(request):
    return Response({"status": "ok", "routing_configured": bool(settings.TOMTOM_API_KEY)})


@api_view(["GET"])
def risk_rules(request):
    """The thresholds and load rules the backend applies, so the UI legend can't drift from them."""
    return Response(rules_as_dict())


class GeocodeView(APIView):
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "geocode"

    def get(self, request):
        try:
            places = providers.geocoder().search(request.query_params.get("q", ""))
        except ProviderError as exc:
            return provider_error_response(exc)
        return Response({"results": [p.__dict__ for p in places]})


class TripPlanViewSet(
    mixins.CreateModelMixin, mixins.RetrieveModelMixin, mixins.ListModelMixin, viewsets.GenericViewSet
):
    """
    list:     GET  /trip-plans/               recent plans (lightweight)
    create:   POST /trip-plans/               compute routes + risk + recommendation
    retrieve: GET  /trip-plans/{id}/          a stored plan (shareable link)
    heatmap:  GET  /trip-plans/{id}/heatmap/  0–48 h corridor weather grid
    """

    queryset = TripPlan.objects.all()
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "plans"

    def get_queryset(self):
        if self.action == "list":
            # Never load the large JSON columns for the history menu.
            return TripPlan.objects.only(
                "id", "created_at", "origin_label", "destination_label", "departure_time", "weather_source"
            )[:10]
        return super().get_queryset()

    def get_serializer_class(self):
        if self.action == "list":
            return TripPlanListSerializer
        if self.action == "create":
            return PlanRequestSerializer
        return TripPlanSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        plan_request = PlanRequest(
            origin=Place(**data["origin"]),
            destination=Place(**data["destination"]),
            departure=data["departure_time"],
            load_lbs=data["load_weight_lbs"],
            interval_miles=data["sample_interval_miles"],
            weather_source=data["weather_source"],
            include_hos=data["include_hos"],
        )
        try:
            result = build_plan(plan_request, providers.routing_provider(), providers.live_weather())
        except ProviderError as exc:
            return provider_error_response(exc)

        plan = TripPlan.objects.create(
            origin_label=plan_request.origin.label,
            origin_lat=plan_request.origin.lat,
            origin_lon=plan_request.origin.lon,
            destination_label=plan_request.destination.label,
            destination_lat=plan_request.destination.lat,
            destination_lon=plan_request.destination.lon,
            departure_time=plan_request.departure,
            load_weight_lbs=plan_request.load_lbs,
            sample_interval_miles=plan_request.interval_miles,
            weather_source=plan_request.weather_source,
            include_hos=plan_request.include_hos,
            recommended_route_id=result["recommended_route_id"],
            result=result,
        )
        return Response(TripPlanSerializer(plan).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["get"])
    def heatmap(self, request, pk=None):
        """Computed on first request and cached on the row, so the routes render without waiting for it."""
        plan = self.get_object()
        if plan.heatmap is None:
            paths = [[(p[1], p[0]) for p in route["path"]] for route in plan.result["routes"]]
            departure = datetime.fromisoformat(plan.result["request"]["departure_time"])
            try:
                plan.heatmap = build_heatmap(
                    paths, departure, plan.load_weight_lbs, providers.weather_for_plan(plan.result)
                )
            except ProviderError as exc:
                return provider_error_response(exc)
            plan.save(update_fields=["heatmap"])
        return Response(plan.heatmap)
