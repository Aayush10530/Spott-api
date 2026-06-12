import logging
from dataclasses import dataclass

import requests
from django.conf import settings

from apps.trip.services.optimizer import haversine_miles  # reuse, never re-implement

logger = logging.getLogger(__name__)


class RoutingError(Exception):
    """Raised when OSRM API is unavailable or returns an error response."""
    pass


@dataclass
class RouteResult:
    """Parsed result from a single OSRM routing API call."""
    polyline:              list[list[float]]   # [[lon, lat], ...] — OSRM coordinate order
    total_distance_miles:  float
    duration_hours:        float
    cumulative_distances:  list[float]         # Mile marker at each polyline point


def get_route(
    start_lat: float,
    start_lon: float,
    finish_lat: float,
    finish_lon: float,
) -> RouteResult:
    """
    Call OSRM routing API exactly once and return structured route data.

    ⚠️  OSRM URL uses lon,lat order (NOT lat,lon):
        /route/v1/driving/{start_lon},{start_lat};{finish_lon},{finish_lat}

    Args:
        start_lat, start_lon:   Starting coordinates
        finish_lat, finish_lon: Destination coordinates

    Returns:
        RouteResult with polyline, distance, duration, and cumulative distances

    Raises:
        RoutingError: On any network failure or non-OK OSRM response
    """
    # Build URL — CRITICAL: lon comes before lat in OSRM
    url = (
        f"{settings.OSRM_BASE_URL}/route/v1/driving/"
        f"{start_lon},{start_lat};{finish_lon},{finish_lat}"
    )
    params = {
        "overview":    "full",
        "geometries":  "geojson",
        "steps":       "false",
    }

    try:
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
    except requests.RequestException as exc:
        raise RoutingError(f"OSRM request failed: {exc}") from exc

    data = response.json()

    if data.get("code") != "Ok" or not data.get("routes"):
        raise RoutingError(
            f"OSRM returned unexpected response: code={data.get('code')}"
        )

    route = data["routes"][0]

    # Extract and convert units
    # OSRM distance is in METERS → convert to miles
    # OSRM duration is in SECONDS → convert to hours
    polyline              = route["geometry"]["coordinates"]   # [[lon, lat], ...]
    total_distance_miles  = route["distance"] / 1609.344
    duration_hours        = route["duration"] / 3600.0
    cumulative_distances  = _compute_cumulative_distances(polyline)

    logger.info(
        f"OSRM route: {total_distance_miles:.1f} miles, "
        f"{duration_hours:.1f} hours, {len(polyline)} waypoints"
    )

    return RouteResult(
        polyline=polyline,
        total_distance_miles=total_distance_miles,
        duration_hours=duration_hours,
        cumulative_distances=cumulative_distances,
    )


def _compute_cumulative_distances(polyline: list[list[float]]) -> list[float]:
    """
    Build a list of running mile-distances from the start of the route
    to each successive polyline point.

    Args:
        polyline: [[lon, lat], ...] — OSRM coordinate order

    Returns:
        List of floats, same length as polyline.
        Index 0 is always 0.0.
        Last index is approximately total_distance_miles.

    Note:
        polyline points are [lon, lat] — we must swap to (lat, lon)
        when calling haversine_miles(lat1, lon1, lat2, lon2).
    """
    if not polyline:
        return []

    distances = [0.0]
    running = 0.0

    for i in range(1, len(polyline)):
        prev_lon, prev_lat = polyline[i - 1]  # OSRM: [lon, lat]
        curr_lon, curr_lat = polyline[i]       # OSRM: [lon, lat]
        # haversine_miles takes (lat, lon) — swap from OSRM [lon, lat]
        segment = haversine_miles(prev_lat, prev_lon, curr_lat, curr_lon)
        running += segment
        distances.append(running)

    return distances
