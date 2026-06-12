from django.apps import AppConfig
import logging

logger = logging.getLogger(__name__)


class TripConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.trip'

    def ready(self):
        # Load all geocoded stations into memory once at startup.
        # Guard against double-loading (Django calls ready() twice in some environments).
        try:
            from apps.trip.services.station_loader import load_stations_into_memory, get_station_count
            if get_station_count() == 0:
                load_stations_into_memory()
        except Exception as e:
            # Do not crash the server if DB isn't ready yet (e.g., during migrations)
            logger.warning(f"Could not load stations into memory at startup: {e}")
