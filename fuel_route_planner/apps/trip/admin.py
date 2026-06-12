# -*- coding: utf-8 -*-
from django.contrib import admin
from .models import FuelStation

@admin.register(FuelStation)
class FuelStationAdmin(admin.ModelAdmin):
    list_display = ['name', 'city', 'state', 'price', 'lat', 'lon', 'geocode_failed']
    list_filter  = ['state', 'geocode_failed']
    search_fields = ['name', 'city', 'state', 'opis_id']
