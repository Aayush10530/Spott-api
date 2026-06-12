import hashlib
import logging

from django.conf import settings
from django.core.cache import cache
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.trip.serializers import TripRequestSerializer
from apps.trip.services.geocoding import geocode_location, GeocodingError
from apps.trip.services.routing import get_route, RoutingError, RouteResult
from apps.trip.services.optimizer import (
    filter_stations_near_route,
    select_optimal_stops,
    FuelStop,
    InfeasibleRouteError,
)
from apps.trip.services.station_loader import get_all_stations

logger = logging.getLogger(__name__)


class TripPlanView(APIView):
    """
    POST /api/v1/trip/plan/

    Accepts start and finish locations, returns optimal fuel stops and route.
    """

    def post(self, request):
        # ── Step 1: Validate input ────────────────────────────────────────────
        serializer = TripRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        start_str  = serializer.validated_data['start']
        finish_str = serializer.validated_data['finish']

        # ── Step 2: Geocode start location ────────────────────────────────────
        try:
            start_coords = geocode_location(start_str)
        except GeocodingError:
            logger.exception(f"Geocoding API failure for start: {start_str}")
            return Response(
                {"error": "Geocoding service unavailable. Please try again later."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        if start_coords is None:
            return Response(
                {"error": f"Could not find location: '{start_str}'. Please use a valid US city and state."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # ── Step 3: Geocode finish location ───────────────────────────────────
        try:
            finish_coords = geocode_location(finish_str)
        except GeocodingError:
            logger.exception(f"Geocoding API failure for finish: {finish_str}")
            return Response(
                {"error": "Geocoding service unavailable. Please try again later."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        if finish_coords is None:
            return Response(
                {"error": f"Could not find location: '{finish_str}'. Please use a valid US city and state."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        start_lat, start_lon   = start_coords
        finish_lat, finish_lon = finish_coords

        # ── Step 4: Check route cache ─────────────────────────────────────────
        cache_key = _build_cache_key(start_lat, start_lon, finish_lat, finish_lon)
        cached_route = cache.get(cache_key)

        if cached_route:
            route_result = RouteResult(**cached_route)
            logger.info(f"Route cache HIT for {start_str} → {finish_str}")
        else:
            # ── Step 5: Call OSRM routing API (ONCE) ─────────────────────────
            try:
                route_result = get_route(start_lat, start_lon, finish_lat, finish_lon)
            except RoutingError as exc:
                logger.exception(f"OSRM routing failure: {exc}")
                return Response(
                    {"error": "Routing service unavailable. Please try again later."},
                    status=status.HTTP_503_SERVICE_UNAVAILABLE,
                )

            # ── Step 6: Cache the route result ────────────────────────────────
            cache.set(
                cache_key,
                {
                    "polyline":             route_result.polyline,
                    "total_distance_miles": route_result.total_distance_miles,
                    "duration_hours":       route_result.duration_hours,
                    "cumulative_distances": route_result.cumulative_distances,
                },
                settings.ROUTE_CACHE_TTL,
            )
            logger.info(f"Route cache MISS — fetched from OSRM for {start_str} → {finish_str}")

        # ── Step 7: Filter stations near the route ────────────────────────────
        all_stations = get_all_stations()
        if not all_stations:
            return Response(
                {"error": "Fuel station data not loaded. Please run: python manage.py load_stations && python manage.py geocode_stations"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        stations_on_route = filter_stations_near_route(
            all_stations=all_stations,
            polyline=route_result.polyline,
            cumulative_distances=route_result.cumulative_distances,
            off_route_threshold_miles=settings.OFF_ROUTE_THRESHOLD_MILES,
        )

        if not stations_on_route:
            return Response(
                {"error": "No fuel stations found near this route. Try a different route."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # ── Step 8: Run the fuel optimization algorithm ───────────────────────
        try:
            fuel_stops = select_optimal_stops(
                stations_on_route=stations_on_route,
                total_distance_miles=route_result.total_distance_miles,
                tank_miles=settings.VEHICLE_TANK_MILES,
                mpg=settings.VEHICLE_MPG,
            )
        except InfeasibleRouteError as exc:
            return Response(
                {"error": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # ── Step 9: Build and return response ─────────────────────────────────
        response_data = _build_response(
            route=route_result,
            fuel_stops=fuel_stops,
            start_str=start_str,
            finish_str=finish_str,
            start_coords=start_coords,
            finish_coords=finish_coords,
        )
        return Response(response_data, status=status.HTTP_200_OK)


# ── Private helpers ───────────────────────────────────────────────────────────

def _build_cache_key(
    start_lat: float,
    start_lon: float,
    finish_lat: float,
    finish_lon: float,
) -> str:
    """Generate a short, deterministic cache key for a route coordinate pair."""
    key_str = f"{start_lat:.4f},{start_lon:.4f},{finish_lat:.4f},{finish_lon:.4f}"
    return f"route:{hashlib.md5(key_str.encode()).hexdigest()}"


def _build_response(
    route: RouteResult,
    fuel_stops: list[FuelStop],
    start_str: str,
    finish_str: str,
    start_coords: tuple[float, float],
    finish_coords: tuple[float, float],
) -> dict:
    """
    Assemble the final JSON response dictionary.
    All monetary values rounded to 2 decimal places.
    All prices rounded to 3 decimal places.
    All distances rounded to 1 decimal place.
    """
    total_gallons = round(sum(s.gallons_to_fill for s in fuel_stops), 2)
    total_cost    = round(sum(s.cost_at_stop    for s in fuel_stops), 2)
    prices        = [s.station.price for s in fuel_stops]

    return {
        "route": {
            "start":               start_str,
            "finish":              finish_str,
            "start_coords":        {"lat": start_coords[0],  "lon": start_coords[1]},
            "finish_coords":       {"lat": finish_coords[0], "lon": finish_coords[1]},
            "total_distance_miles": round(route.total_distance_miles, 1),
            "duration_hours":       round(route.duration_hours, 1),
            "polyline":             route.polyline,  # [[lon, lat], ...] for map rendering
        },
        "fuel_stops": [
            {
                "order":                  stop.order,
                "station_name":           stop.station.name,
                "address":                stop.station.address,
                "city":                   stop.station.city,
                "state":                  stop.station.state,
                "lat":                    stop.station.lat,
                "lon":                    stop.station.lon,
                "price_per_gallon":       round(stop.station.price, 3),
                "gallons_to_fill":        stop.gallons_to_fill,
                "cost_at_stop":           stop.cost_at_stop,
                "route_mile_marker":      round(stop.station.route_mile, 1),
                "fuel_level_after_miles": stop.fuel_level_after,
            }
            for stop in fuel_stops
        ],
        "summary": {
            "total_stops":              len(fuel_stops),
            "total_gallons":            total_gallons,
            "total_fuel_cost":          total_cost,
            "avg_price_per_gallon":     round(total_cost / total_gallons, 3) if total_gallons > 0 else 0,
            "cheapest_stop_price":      round(min(prices), 3) if prices else None,
            "most_expensive_stop_price": round(max(prices), 3) if prices else None,
        },
    }
