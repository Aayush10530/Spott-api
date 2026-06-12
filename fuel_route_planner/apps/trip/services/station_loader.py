# -*- coding: utf-8 -*-
import logging

logger = logging.getLogger(__name__)

_STATION_CACHE: list[dict] = []

def load_stations_into_memory() -> None:
    """
    Query the database for all geocoded FuelStation records and populate
    _STATION_CACHE. Called once at server startup via TripConfig.ready().
    Only loads stations where lat and lon are set and geocode_failed is False.
    """
    global _STATION_CACHE
    from apps.trip.models import FuelStation

    qs = FuelStation.objects.filter(
        geocode_failed=False,
        lat__isnull=False,
        lon__isnull=False,
    ).values('opis_id', 'name', 'address', 'city', 'state', 'lat', 'lon', 'price')

    _STATION_CACHE = list(qs)
    logger.info(f"Loaded {len(_STATION_CACHE)} fuel stations into memory.")

def get_all_stations() -> list[dict]:
    """Return the full in-memory station list."""
    return _STATION_CACHE

def get_station_count() -> int:
    """Return number of stations currently in memory."""
    return len(_STATION_CACHE)
