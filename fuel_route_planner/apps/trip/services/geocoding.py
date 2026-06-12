import logging
import requests
from django.conf import settings

logger = logging.getLogger(__name__)

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"


class GeocodingError(Exception):
    """Raised when Nominatim API call fails due to a network or HTTP error."""
    pass


def _call_nominatim(query: str) -> tuple[float, float] | None:
    """
    Internal helper: make one Nominatim API call.
    Returns (lat, lon) as floats if found, None if not found.
    Raises GeocodingError on network/HTTP failure.
    Does NOT sleep — caller's responsibility in batch scenarios.
    """
    headers = {"User-Agent": settings.NOMINATIM_USER_AGENT}
    params  = {"q": query, "format": "json", "limit": 1, "countrycodes": "us"}

    try:
        resp = requests.get(NOMINATIM_URL, params=params, headers=headers, timeout=10)
        resp.raise_for_status()
    except requests.RequestException as exc:
        raise GeocodingError(f"Nominatim request failed for '{query}': {exc}") from exc

    results = resp.json()
    if not results:
        return None

    return float(results[0]["lat"]), float(results[0]["lon"])


def geocode_location(location_str: str) -> tuple[float, float] | None:
    """
    Geocode a free-form US location string (e.g., "New York, NY").
    Used per-request for the user's start and finish inputs.
    Returns (lat, lon) or None if not found.
    Raises GeocodingError on API failure.
    """
    return _call_nominatim(location_str)


def geocode_city_state(city: str, state: str) -> tuple[float, float] | None:
    """
    Geocode a city+state pair (e.g., city="Chicago", state="IL").
    Used by the geocode_stations management command.
    Returns (lat, lon) or None if not found.
    Raises GeocodingError on API failure.
    NOTE: Caller MUST sleep(1.0) between calls to respect Nominatim rate limits.
    """
    query = f"{city}, {state}, USA"
    return _call_nominatim(query)
