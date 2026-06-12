import logging
import time
from collections import defaultdict

from django.core.management.base import BaseCommand

from apps.trip.models import FuelStation
from apps.trip.services.geocoding import geocode_city_state, GeocodingError

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = (
        'Geocode all FuelStation records by city+state using Nominatim. '
        'Rate-limited to 1 request/second as required by Nominatim terms of service. '
        'Estimated runtime: ~64 minutes for ~3,813 unique city+state combos. '
        'Run once after load_stations. Use --resume to skip already-geocoded combos.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--limit',
            type=int,
            default=None,
            help='Only geocode the first N unique city+state combos (for testing).',
        )
        parser.add_argument(
            '--resume',
            action='store_true',
            default=False,
            help='Skip city+state combos where at least one station already has a lat/lon set.',
        )

    def handle(self, *args, **options):
        limit  = options['limit']
        resume = options['resume']

        # Build list of unique (city, state) combos that still need geocoding
        if resume:
            qs = FuelStation.objects.filter(geocode_failed=False, lat__isnull=True)
        else:
            qs = FuelStation.objects.filter(geocode_failed=False)

        # Group station IDs by city+state
        combo_map: dict[tuple, list[int]] = defaultdict(list)
        for station in qs.values('id', 'city', 'state'):
            key = (station['city'], station['state'])
            combo_map[key].append(station['id'])

        combos = list(combo_map.keys())
        if limit:
            combos = combos[:limit]

        total    = len(combos)
        success  = 0
        failed   = 0

        self.stdout.write(
            f"Geocoding {total} unique city+state combos "
            f"(~{total} seconds ~ {total // 60}m {total % 60}s) ..."
        )

        for i, (city, state) in enumerate(combos, 1):
            try:
                result = geocode_city_state(city, state)
            except GeocodingError as exc:
                self.stdout.write(
                    self.style.WARNING(f"  API error for {city}, {state}: {exc}")
                )
                # Mark as failed so we skip on future --resume runs
                FuelStation.objects.filter(id__in=combo_map[(city, state)]).update(
                    geocode_failed=True
                )
                failed += 1
            else:
                if result:
                    lat, lon = result
                    FuelStation.objects.filter(id__in=combo_map[(city, state)]).update(
                        lat=lat, lon=lon
                    )
                    self.stdout.write(f"  [OK] [{i}/{total}] {city}, {state} -> ({lat:.4f}, {lon:.4f})")
                    success += 1
                else:
                    FuelStation.objects.filter(id__in=combo_map[(city, state)]).update(
                        geocode_failed=True
                    )
                    self.stdout.write(
                        self.style.WARNING(f"  [FAIL] [{i}/{total}] Not found: {city}, {state}")
                    )
                    failed += 1

            # ! MANDATORY: Nominatim enforces 1 request/second rate limit
            time.sleep(1.0)

        remaining = FuelStation.objects.filter(geocode_failed=False, lat__isnull=True).count()
        self.stdout.write(
            self.style.SUCCESS(
                f"\nDone. Geocoded: {success}/{total}. Failed: {failed}. "
                f"Remaining ungeooded: {remaining}."
            )
        )
