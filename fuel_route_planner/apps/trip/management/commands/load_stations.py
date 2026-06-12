# -*- coding: utf-8 -*-
import csv
import logging

from django.conf import settings
from django.core.management.base import BaseCommand

from apps.trip.models import FuelStation

logger = logging.getLogger(__name__)

US_STATES = {
    'AL','AK','AZ','AR','CA','CO','CT','DE','FL','GA',
    'HI','ID','IL','IN','IA','KS','KY','LA','ME','MD',
    'MA','MI','MN','MS','MO','MT','NE','NV','NH','NJ',
    'NM','NY','NC','ND','OH','OK','OR','PA','RI','SC',
    'SD','TN','TX','UT','VT','VA','WA','WV','WI','WY',
}

class Command(BaseCommand):
    help = 'Load fuel stations from CSV into the database. Idempotent - safe to re-run.'

    def handle(self, *args, **options):
        csv_path = settings.FUEL_CSV_PATH

        if not csv_path.exists():
            self.stdout.write(self.style.ERROR(f"CSV not found at: {csv_path}"))
            return

        self.stdout.write(f"Reading {csv_path} ...")

        station_map: dict[str, dict] = {}
        skipped_non_us = 0
        skipped_bad_price = 0
        total_rows = 0

        with open(csv_path, newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                total_rows += 1

                state = row.get('State', '').strip()
                if state not in US_STATES:
                    skipped_non_us += 1
                    continue

                raw_price = row.get('Retail Price', '').strip()
                try:
                    price = float(raw_price)
                except (ValueError, TypeError):
                    skipped_bad_price += 1
                    continue

                opis_id = row.get('OPIS Truckstop ID', '').strip()
                if not opis_id:
                    continue

                if opis_id not in station_map or price < station_map[opis_id]['price']:
                    station_map[opis_id] = {
                        'opis_id': opis_id,
                        'name':    row.get('Truckstop Name', '').strip(),
                        'address': row.get('Address', '').strip(),
                        'city':    row.get('City', '').strip(),
                        'state':   state,
                        'rack_id': row.get('Rack ID', '').strip(),
                        'price':   price,
                    }

        self.stdout.write(
            f"Parsed {total_rows} rows -> "
            f"{len(station_map)} unique US stations "
            f"(skipped {skipped_non_us} non-US, {skipped_bad_price} bad prices)"
        )

        created = updated = 0
        for i, (opis_id, data) in enumerate(station_map.items(), 1):
            obj, was_created = FuelStation.objects.update_or_create(
                opis_id=opis_id,
                defaults={
                    'name':    data['name'],
                    'address': data['address'],
                    'city':    data['city'],
                    'state':   data['state'],
                    'rack_id': data['rack_id'],
                    'price':   data['price'],
                                                                     
                },
            )
                                                                                               
            if not was_created and obj.price > data['price']:
                obj.price = data['price']
                obj.save(update_fields=['price'])

            if was_created:
                created += 1
            else:
                updated += 1

            if i % 500 == 0:
                self.stdout.write(f"  Processed {i}/{len(station_map)} ...")

        self.stdout.write(
            self.style.SUCCESS(
                f"Done. Created: {created}, Updated: {updated}, Total: {created + updated}"
            )
        )
