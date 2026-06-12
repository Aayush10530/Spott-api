# -*- coding: utf-8 -*-
from django.db import models

class FuelStation(models.Model):
    """
    One record per unique truckstop (OPIS Truckstop ID).
    Loaded from fuel-prices-for-be-assessment.csv by the load_stations command.
    lat/lon populated later by the geocode_stations command.
    """
    opis_id        = models.CharField(max_length=20, unique=True)                      
    name           = models.CharField(max_length=255)                               
    address        = models.CharField(max_length=255, blank=True)            
    city           = models.CharField(max_length=100)                     
    state          = models.CharField(max_length=2)                                         
    rack_id        = models.CharField(max_length=20, blank=True)             
    price          = models.FloatField()                                                                
    lat            = models.FloatField(null=True, blank=True)                                      
    lon            = models.FloatField(null=True, blank=True)                                      
    geocode_failed = models.BooleanField(default=False)                                               

    class Meta:
        indexes = [
            models.Index(fields=['state']),
            models.Index(fields=['lat', 'lon']),
            models.Index(fields=['geocode_failed']),
        ]

    def __str__(self):
        return f"{self.name} ({self.city}, {self.state}) - ${self.price:.3f}"
