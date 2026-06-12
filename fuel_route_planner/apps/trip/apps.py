from django.apps import AppConfig
import logging

logger = logging.getLogger(__name__)


class TripConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.trip'

    def ready(self):
        from django.db import OperationalError, ProgrammingError
        try:
            from apps.trip.services.station_loader import (
                load_stations_into_memory,
                get_station_count,
            )
            if get_station_count() == 0:
                load_stations_into_memory()
        except (OperationalError, ProgrammingError):
            # Tables do not exist yet - happens during migrate, safe to ignore
            pass
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(
                f"Could not load stations into memory at startup: {e}"
            )
