# ARCHITECTURE.md
# Fuel Route Planner — Architecture Reference

> This file is the technical blueprint. Every module, function, and data flow is defined here.
> AI code generators MUST follow this structure exactly. Do not invent new layers.

---

## Layer Diagram

```
┌─────────────────────────────────────────────────────────┐
│                    HTTP REQUEST LAYER                    │
│         POST /api/v1/trip/plan/ (Postman / Client)       │
└───────────────────────────┬─────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────┐
│                    VIEW LAYER                            │
│            apps/trip/views.py :: TripPlanView            │
│  - Input validation (via serializer)                     │
│  - Orchestrates service calls                            │
│  - Returns JSON response                                 │
└──────┬──────────────────┬──────────────────┬────────────┘
       │                  │                  │
┌──────▼──────┐  ┌────────▼───────┐  ┌──────▼──────────┐
│  geocoding  │  │    routing     │  │   optimizer     │
│  .py        │  │    .py         │  │   .py           │
│             │  │                │  │                 │
│ Nominatim   │  │ OSRM API       │  │ Fuel stop       │
│ geocoding   │  │ single call    │  │ selection       │
│ for start/  │  │ returns route  │  │ algorithm       │
│ finish      │  │ geometry +     │  │ (greedy         │
│             │  │ distance       │  │  look-ahead)    │
└──────┬──────┘  └────────┬───────┘  └──────┬──────────┘
       │                  │                  │
┌──────▼──────────────────▼──────────────────▼──────────┐
│                 DATA LAYER                              │
│                                                         │
│  SQLite DB (FuelStation model)        In-Memory Cache   │
│  ← populated by management cmds      ← loaded at       │
│  ← source of truth for station data    app startup      │
│  ← queried ONLY by management cmds   ← queried during  │
│    and on app startup                  every request    │
└─────────────────────────────────────────────────────────┘
```

---

## Module Specifications

### `config/settings.py`
Single settings file. No dev/prod split (assessment scope).

```python
# Key settings to define:
INSTALLED_APPS = [
    ...,
    'rest_framework',
    'apps.trip',
]

REST_FRAMEWORK = {
    'DEFAULT_RENDERER_CLASSES': ['rest_framework.renderers.JSONRenderer'],
    'DEFAULT_PARSER_CLASSES': ['rest_framework.parsers.JSONParser'],
}

CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'fuel-planner-cache',
    }
}

# From .env
NOMINATIM_USER_AGENT = env('NOMINATIM_USER_AGENT', default='FuelRoutePlanner/1.0')
OSRM_BASE_URL = env('OSRM_BASE_URL', default='http://router.project-osrm.org')

# Constants (not from env — fixed business rules)
VEHICLE_TANK_MILES = 500        # max range on full tank
VEHICLE_MPG = 10                # fuel efficiency
OFF_ROUTE_THRESHOLD_MILES = 50  # max distance from route to include a station
ROUTE_CACHE_TTL = 3600          # 1 hour cache for OSRM responses
```

---

### `apps/trip/models.py`

**Only one model in this project.**

```python
class FuelStation(models.Model):
    opis_id       = models.CharField(max_length=20, unique=True)
    name          = models.CharField(max_length=255)
    address       = models.CharField(max_length=255)
    city          = models.CharField(max_length=100)
    state         = models.CharField(max_length=2)
    rack_id       = models.CharField(max_length=20, blank=True)
    price         = models.FloatField()           # cheapest price at this station
    lat           = models.FloatField(null=True)  # populated by geocode_stations cmd
    lon           = models.FloatField(null=True)  # populated by geocode_stations cmd
    geocode_failed = models.BooleanField(default=False)  # True = Nominatim returned nothing

    class Meta:
        indexes = [
            models.Index(fields=['state']),
            models.Index(fields=['geocode_failed']),
        ]

    def __str__(self):
        return f"{self.name} ({self.city}, {self.state}) — ${self.price:.3f}"
```

---

### `apps/trip/apps.py`

**Critical file.** Loads all geocoded stations into a module-level list on server startup.

```python
from django.apps import AppConfig

class TripConfig(AppConfig):
    name = 'apps.trip'

    def ready(self):
        # Import here to avoid circular imports
        from apps.trip.services.station_loader import load_stations_into_memory
        load_stations_into_memory()
```

---

### `apps/trip/services/station_loader.py`

**Purpose:** Manages the in-memory station cache. Called once at startup.

```python
# Module-level cache (lives for entire process lifetime)
_STATION_CACHE: list[dict] = []

def load_stations_into_memory() -> None:
    """
    Load all geocoded FuelStation records from DB into _STATION_CACHE.
    Called once at startup via TripConfig.ready().
    Skips stations with geocode_failed=True or missing lat/lon.
    Logs count of loaded stations.
    """

def get_all_stations() -> list[dict]:
    """
    Return the in-memory station list.
    Each dict has: opis_id, name, address, city, state, lat, lon, price
    """

def get_station_count() -> int:
    """Return number of loaded stations (for health checks / logging)."""
```

---

### `apps/trip/services/geocoding.py`

**Purpose:** Thin wrapper around Nominatim. Two use cases: single geocode (per request) and batch geocode (management command).

```python
import time
import requests
from django.conf import settings

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"

def geocode_location(location_str: str) -> tuple[float, float] | None:
    """
    Geocode a single location string (e.g., "New York, NY").
    Returns (lat, lon) tuple or None if not found.
    Makes exactly 1 HTTP call.
    Used by: TripPlanView per request (for start + finish)
    
    Args:
        location_str: Human-readable US location string
    
    Returns:
        (lat, lon) as floats, or None if geocoding fails
    
    Raises:
        GeocodingError: If API call fails (not same as returning None)
    """

def geocode_city_state(city: str, state: str) -> tuple[float, float] | None:
    """
    Geocode a city+state combo (used by management command).
    Returns (lat, lon) or None.
    Caller is responsible for rate-limiting (sleep(1)).
    """

class GeocodingError(Exception):
    """Raised when Nominatim API call fails (network error, 5xx, etc.)"""
    pass
```

---

### `apps/trip/services/routing.py`

**Purpose:** Wraps OSRM. Called ONCE per trip plan. Returns parsed route data.

```python
import requests
from django.conf import settings
from dataclasses import dataclass

@dataclass
class RouteResult:
    polyline: list[list[float]]        # [[lon, lat], [lon, lat], ...]  OSRM order
    total_distance_miles: float
    duration_hours: float
    cumulative_distances: list[float]  # mile marker at each polyline point

def get_route(
    start_lat: float, start_lon: float,
    finish_lat: float, finish_lon: float
) -> RouteResult:
    """
    Call OSRM routing API. Returns full route geometry + distances.
    
    OSRM URL pattern:
    {base}/route/v1/driving/{start_lon},{start_lat};{finish_lon},{finish_lat}
    ?overview=full&geometries=geojson&steps=false
    
    NOTE: OSRM uses lon,lat order in URL (opposite of standard lat,lon)
    
    After getting response:
    - Extract geometry.coordinates (list of [lon, lat])
    - Convert distance from meters to miles (divide by 1609.344)
    - Convert duration from seconds to hours (divide by 3600)
    - Compute cumulative_distances: running haversine sum along polyline points
    
    Returns: RouteResult dataclass
    
    Raises:
        RoutingError: If OSRM returns non-200 or code != 'Ok'
    """

def compute_cumulative_distances(polyline: list[list[float]]) -> list[float]:
    """
    Given a list of [lon, lat] points, compute the running distance from
    the first point to each subsequent point (in miles).
    
    Returns list of floats, same length as polyline.
    cumulative_distances[0] = 0.0 (always)
    cumulative_distances[-1] ≈ total_distance_miles
    
    Uses haversine formula internally.
    """

class RoutingError(Exception):
    """Raised when OSRM API is unavailable or returns an error."""
    pass
```

---

### `apps/trip/services/optimizer.py`

**Purpose:** The fuel stop selection algorithm. Pure Python, no external dependencies.
This is the most important service.

```python
from dataclasses import dataclass
from math import radians, sin, cos, sqrt, atan2

EARTH_RADIUS_MILES = 3958.8

@dataclass
class StationOnRoute:
    """A fuel station projected onto the route."""
    opis_id: str
    name: str
    address: str
    city: str
    state: str
    lat: float
    lon: float
    price: float
    route_mile: float           # Distance from route start to this station's nearest point
    deviation_miles: float      # How far off-route this station is

@dataclass
class FuelStop:
    """A chosen fuel stop with purchase details."""
    order: int
    station: StationOnRoute
    gallons_to_fill: float
    cost_at_stop: float
    fuel_level_after: float     # remaining range in miles after fill

def haversine_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calculate great-circle distance between two points in miles.
    Standard haversine formula. Used extensively — keep it fast.
    """

def filter_stations_near_route(
    all_stations: list[dict],
    polyline: list[list[float]],          # [lon, lat] pairs from OSRM
    cumulative_distances: list[float],
    off_route_threshold_miles: float = 50.0,
) -> list[StationOnRoute]:
    """
    STEP 1: Bounding box pre-filter
      - Find route bounding box (min/max lat, min/max lon)
      - Add 2-degree buffer on all sides
      - Reject any station outside this box BEFORE running haversine
      - Eliminates ~70-80% of stations instantly
    
    STEP 2: Haversine distance to nearest route point
      - For each remaining station, find nearest polyline point
      - Record route_mile at that nearest point (from cumulative_distances)
      - Record deviation_miles (actual distance from station to route)
    
    STEP 3: Threshold filter
      - Keep only stations where deviation_miles <= off_route_threshold_miles
    
    STEP 4: Sort by route_mile
      - Return sorted list (ascending) of StationOnRoute
    
    Performance note:
      - Bounding box check: O(1) per station, no trig
      - Haversine: only for stations inside bounding box
      - Typical NY-LA: ~400-600 stations survive bounding box → haversine applied to those
    """

def select_optimal_stops(
    stations_on_route: list[StationOnRoute],
    total_distance_miles: float,
    tank_miles: float = 500.0,
    mpg: float = 10.0,
) -> list[FuelStop]:
    """
    GREEDY LOOK-AHEAD ALGORITHM:
    
    State:
      - current_mile: position along route (starts at 0)
      - current_fuel_miles: remaining range (starts at tank_miles = 500)
    
    Loop:
      while current_mile + current_fuel_miles < total_distance:
          
          # All stations within current fuel range
          reachable = [s for s in stations_on_route
                       if current_mile < s.route_mile <= current_mile + current_fuel_miles]
          
          if not reachable:
              raise InfeasibleRouteError(current_mile)
          
          # Full look-ahead window: stations within FULL TANK from current position
          # (These are all stations we could potentially reach if we fill up here)
          full_window = [s for s in stations_on_route
                         if current_mile < s.route_mile <= current_mile + tank_miles]
          
          # Find cheapest in full window
          cheapest_in_window = min(full_window, key=lambda s: s.price)
          
          # Can we reach cheapest_in_window?
          can_reach_cheapest = (cheapest_in_window.route_mile - current_mile) <= current_fuel_miles
          
          if can_reach_cheapest:
              target_station = cheapest_in_window
          else:
              # We can't reach cheapest in full window.
              # Must stop somewhere before running out.
              # Pick the cheapest station we CAN actually reach right now.
              target_station = min(reachable, key=lambda s: s.price)
          
          # Travel to target_station
          miles_traveled = target_station.route_mile - current_mile
          current_fuel_miles -= miles_traveled
          current_mile = target_station.route_mile
          
          # Decide how much to fill at this stop
          # Look ahead from target: is there a cheaper station within tank range?
          next_window = [s for s in stations_on_route
                         if current_mile < s.route_mile <= current_mile + tank_miles]
          
          if not next_window:
              # No more stations ahead — fill up completely to reach destination
              fill_miles = tank_miles - current_fuel_miles
          else:
              next_cheaper = [s for s in next_window if s.price < target_station.price]
              if not next_cheaper:
                  # Current station is cheapest in next 500 miles → fill completely
                  fill_miles = tank_miles - current_fuel_miles
              else:
                  # A cheaper station is ahead.
                  # Fill just enough to reach it (with 10-mile safety buffer)
                  nearest_cheaper = min(next_cheaper, key=lambda s: s.route_mile)
                  needed = nearest_cheaper.route_mile - current_mile - current_fuel_miles + 10
                  fill_miles = max(0.0, min(needed, tank_miles - current_fuel_miles))
                  
                  # Safety check: ensure we have enough to at least reach a station
                  # (fill_miles can be 0 if we already have enough fuel to reach cheaper stop)
          
          gallons = fill_miles / mpg
          cost = gallons * target_station.price
          current_fuel_miles += fill_miles
          
          fuel_stops.append(FuelStop(
              order=len(fuel_stops) + 1,
              station=target_station,
              gallons_to_fill=round(gallons, 2),
              cost_at_stop=round(cost, 2),
              fuel_level_after=round(current_fuel_miles, 1),
          ))
      
      return fuel_stops
    
    Raises:
        InfeasibleRouteError: if no station reachable before fuel runs out
    """

class InfeasibleRouteError(Exception):
    """
    Raised when the route cannot be completed.
    Should be caught in view and returned as 400 error.
    """
    def __init__(self, stuck_at_mile: float):
        self.stuck_at_mile = stuck_at_mile
        super().__init__(f"No fuel station within 500 miles after mile {stuck_at_mile:.0f}")
```

---

### `apps/trip/views.py`

**Purpose:** Orchestrates the request. Thin. No business logic here.

```python
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.core.cache import cache
import hashlib

class TripPlanView(APIView):
    """
    POST /api/v1/trip/plan/
    
    Orchestration flow:
    1. Validate request body with TripRequestSerializer
    2. Geocode start (Nominatim)
    3. Geocode finish (Nominatim)
    4. Check Django cache for this (start_coords, finish_coords) pair
    5. If cache miss: call OSRM routing API
    6. Store route in cache
    7. Filter stations near route (station_loader + optimizer)
    8. Run optimization algorithm
    9. Serialize and return response
    
    Error handling:
    - ValidationError → 400
    - GeocodingError (API failure) → 503
    - None from geocode_location → 400 "could not geocode"
    - RoutingError → 503
    - InfeasibleRouteError → 400
    
    Cache key:
    hashlib.md5(f"{start_lat:.4f},{start_lon:.4f},{finish_lat:.4f},{finish_lon:.4f}".encode()).hexdigest()
    """

def _build_cache_key(start_lat, start_lon, finish_lat, finish_lon) -> str:
    """Generate deterministic cache key for a route."""

def _build_response(route_result, fuel_stops, start_str, finish_str, start_coords, finish_coords) -> dict:
    """
    Build the final JSON response dict.
    Calculates:
      - total_gallons: sum of gallons across all stops
      - total_fuel_cost: sum of costs across all stops
      - avg_price_per_gallon: total_cost / total_gallons
      - most_expensive_stop: max price across stops
      - cheapest_stop: min price across stops
    """
```

---

### `apps/trip/serializers.py`

```python
from rest_framework import serializers

class TripRequestSerializer(serializers.Serializer):
    start = serializers.CharField(
        max_length=200,
        help_text="Starting location within the USA (e.g., 'New York, NY')"
    )
    finish = serializers.CharField(
        max_length=200,
        help_text="Destination within the USA (e.g., 'Los Angeles, CA')"
    )

    def validate_start(self, value):
        if not value.strip():
            raise serializers.ValidationError("Start location cannot be blank.")
        return value.strip()

    def validate_finish(self, value):
        if not value.strip():
            raise serializers.ValidationError("Finish location cannot be blank.")
        return value.strip()

    def validate(self, data):
        if data.get('start', '').lower() == data.get('finish', '').lower():
            raise serializers.ValidationError("Start and finish locations must be different.")
        return data
```

---

### `apps/trip/management/commands/load_stations.py`

```python
"""
python manage.py load_stations

Reads data/fuel-prices.csv (path relative to project root).
Deduplicates by OPIS Truckstop ID (keeps minimum price).
Filters to US states only.
Creates/updates FuelStation records. Idempotent (safe to re-run).
Uses bulk_create with update_conflicts for performance.
Prints summary: total rows processed, unique stations created, skipped duplicates.
"""
```

---

### `apps/trip/management/commands/geocode_stations.py`

```python
"""
python manage.py geocode_stations [--limit N] [--resume]

Groups FuelStation records by unique (city, state) combination.
For each unique combo:
  1. Check if already geocoded (skip if lat/lon already set)
  2. Call geocode_city_state(city, state) from geocoding service
  3. time.sleep(1.0) MANDATORY between calls (Nominatim rate limit)
  4. If result found: update all stations in that city+state with lat/lon
  5. If no result: mark all stations as geocode_failed=True
  6. Print progress: "Geocoded: city, STATE → (lat, lon)" or "Failed: city, STATE"

--limit N: Only geocode first N unique combos (for testing)
--resume: Skip city+state combos where at least one station already has lat/lon

Total combos to geocode: ~3,813
Estimated runtime: ~64 minutes (one-time operation)

Uses Django's update() for bulk updates per city+state group (single DB query per group).
"""
```

---

### `apps/trip/urls.py`

```python
from django.urls import path
from .views import TripPlanView

urlpatterns = [
    path('plan/', TripPlanView.as_view(), name='trip-plan'),
]
```

### `config/urls.py`

```python
from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/v1/trip/', include('apps.trip.urls')),
]
```

---

## Data Flow: Per-Request Sequence

```
TripPlanView.post()
    │
    ├── TripRequestSerializer.validate(request.data)
    │       └── Returns: { start: str, finish: str }
    │
    ├── geocoding.geocode_location(start)  → (start_lat, start_lon)
    ├── geocoding.geocode_location(finish) → (finish_lat, finish_lon)
    │
    ├── cache.get(cache_key)
    │       ├── HIT  → deserialize RouteResult from cache
    │       └── MISS → routing.get_route(start_lat, start_lon, finish_lat, finish_lon)
    │                       └── Returns RouteResult(polyline, total_distance_miles,
    │                                                duration_hours, cumulative_distances)
    │                   cache.set(cache_key, route_result, ROUTE_CACHE_TTL)
    │
    ├── station_loader.get_all_stations()  → list[dict]  (in-memory, instant)
    │
    ├── optimizer.filter_stations_near_route(all_stations, polyline, cumulative_distances)
    │       └── Returns: list[StationOnRoute] (sorted by route_mile)
    │
    ├── optimizer.select_optimal_stops(stations_on_route, total_distance_miles)
    │       └── Returns: list[FuelStop]
    │
    └── _build_response(...)
            └── Returns: JSON dict → HTTP 200
```

---

## Data Flow: Setup Commands Sequence

```
manage.py load_stations
    │
    ├── Open data/fuel-prices.csv
    ├── Filter US states only
    ├── Group by OPIS Truckstop ID → keep min price
    ├── bulk_create FuelStation records (lat=None, lon=None)
    └── Print: "Created 6626 fuel stations."

manage.py geocode_stations
    │
    ├── Query FuelStation.objects.filter(geocode_failed=False, lat__isnull=True)
    ├── Group by (city, state)  → ~3,813 unique combos
    ├── For each combo (with sleep(1) between calls):
    │       ├── geocoding.geocode_city_state(city, state)
    │       ├── If (lat, lon): FuelStation.objects.filter(city=city,state=state).update(lat=lat, lon=lon)
    │       └── If None:       FuelStation.objects.filter(city=city,state=state).update(geocode_failed=True)
    └── Print: "Geocoded: 3654/3813. Failed: 159."

manage.py runserver
    │
    └── TripConfig.ready()
            └── station_loader.load_stations_into_memory()
                    ├── FuelStation.objects.filter(lat__isnull=False, geocode_failed=False).values(...)
                    └── Populate _STATION_CACHE list
                        Print: "Loaded 6401 stations into memory."
```

---

## Error Handling Matrix

| Scenario | Where Raised | HTTP Code | Message |
|----------|-------------|-----------|---------|
| Missing start or finish field | Serializer | 400 | DRF validation error |
| Start == Finish | Serializer | 400 | "Start and finish must be different" |
| Nominatim returns nothing | View | 400 | "Could not geocode: {location}" |
| Nominatim API failure | View | 503 | "Geocoding service unavailable" |
| OSRM API failure | View | 503 | "Routing service unavailable" |
| OSRM returns error code | View | 503 | "Could not compute route" |
| Gap in stations > 500 mi | View (catch InfeasibleRouteError) | 400 | Algorithm error message |
| No stations on route at all | View | 400 | "No fuel stations found near this route" |
