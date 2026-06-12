from django.db import models


class FuelStation(models.Model):
    """
    One record per unique truckstop (OPIS Truckstop ID).
    Loaded from fuel-prices-for-be-assessment.csv by the load_stations command.
    lat/lon populated later by the geocode_stations command.
    """
    opis_id        = models.CharField(max_length=20, unique=True)   # OPIS Truckstop ID
    name           = models.CharField(max_length=255)               # Truckstop Name
    address        = models.CharField(max_length=255, blank=True)   # Address
    city           = models.CharField(max_length=100)               # City
    state          = models.CharField(max_length=2)                 # 2-letter US state code
    rack_id        = models.CharField(max_length=20, blank=True)    # Rack ID
    price          = models.FloatField()                            # Cheapest Retail Price at this stop
    lat            = models.FloatField(null=True, blank=True)       # Populated by geocode_stations
    lon            = models.FloatField(null=True, blank=True)       # Populated by geocode_stations
    geocode_failed = models.BooleanField(default=False)            # True = Nominatim returned nothing

    class Meta:
        indexes = [
            models.Index(fields=['state']),
            models.Index(fields=['lat', 'lon']),
            models.Index(fields=['geocode_failed']),
        ]

    def __str__(self):
        return f"{self.name} ({self.city}, {self.state}) — ${self.price:.3f}"
