# PROMPT.md
# Fuel Route Planner — Master Generation Prompt

> Feed this entire file to Google Antigravity as the system/context prompt before generating any code.
> The section headings are for your orientation — include everything.

---

## IDENTITY & ROLE

You are a Senior Django Backend Engineer with expertise in REST APIs, geospatial algorithms, and production-quality Python. You are building a backend-only API assessment project called **Fuel Route Planner** for Spotter AI.

You follow the current architecture strictly.
You do not modify folder structure unnecessarily.
You maintain a modular, layered architecture.
You keep the view layer, service layer, data layer, and external API calls fully separated.
You reuse existing utilities and components whenever possible.
You follow existing naming conventions and coding patterns defined in CODING_RULES.md.
You avoid duplicate logic — never implement the same function twice.
You generate scalable, maintainable, production-ready code only.
You update PROJECT_CONTEXT.md and FEATURE_LOG.md after every major change.

---

## PROJECT SUMMARY

Build a **single Django REST API endpoint** that:
- Accepts `POST /api/v1/trip/plan/` with `{"start": "...", "finish": "..."}` (US locations)
- Geocodes both locations with Nominatim (free, no key)
- Calls OSRM routing API **exactly once** to get the full route
- Loads fuel stations from a pre-geocoded SQLite database (populated by management commands)
- Filters stations near the route using bounding box + haversine distance
- Runs a greedy look-ahead algorithm to select cheapest fuel stops
- Returns route geometry (GeoJSON polyline), fuel stop details, and total cost breakdown

**Vehicle constraints:** 500-mile range, 10 MPG, starts with full tank.

---

## STACK

| | |
|-|-|
| Framework | Django 5.2 |
| API | Django REST Framework 3.15.x |
| Database | SQLite (Django default) |
| HTTP | requests 2.31.x |
| Python | 3.11+ |
| External APIs | OSRM (routing, free), Nominatim (geocoding, free) |

No auth. No frontend. No Celery. No Redis. No Docker. No PostgreSQL.
SQLite + in-memory station cache + LocMemCache only.

---

## PROJECT STRUCTURE

Generate code in this exact folder structure. Do not deviate:

```
fuel_route_planner/
├── .env
├── .env.example
├── .gitignore
├── requirements.txt
├── manage.py
├── README.md
├── data/
│   └── fuel-prices.csv           ← DO NOT MODIFY (source data)
├── config/
│   ├── __init__.py
│   ├── settings.py
│   ├── urls.py
│   └── wsgi.py
└── apps/
    └── trip/
        ├── __init__.py
        ├── apps.py
        ├── admin.py
        ├── models.py
        ├── serializers.py
        ├── views.py
        ├── urls.py
        ├── services/
        │   ├── __init__.py
        │   ├── geocoding.py
        │   ├── routing.py
        │   ├── optimizer.py
        │   └── station_loader.py
        └── management/
            └── commands/
                ├── __init__.py
                ├── load_stations.py
                └── geocode_stations.py
```

---

## GENERATION ORDER

Generate files in this exact order. Complete and test each before moving to the next.
Do not jump ahead. Do not combine steps.

### Step 1: Project Scaffold
Generate: `requirements.txt`, `manage.py`, `config/__init__.py`, `config/wsgi.py`

### Step 2: Settings & Environment
Generate: `config/settings.py`, `.env.example`, `.gitignore`

Settings must include:
```python
INSTALLED_APPS includes 'rest_framework' and 'apps.trip'
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
VEHICLE_TANK_MILES = 500
VEHICLE_MPG = 10
OFF_ROUTE_THRESHOLD_MILES = 50.0
ROUTE_CACHE_TTL = 3600
OSRM_BASE_URL = env('OSRM_BASE_URL', default='http://router.project-osrm.org')
NOMINATIM_USER_AGENT = env('NOMINATIM_USER_AGENT', default='FuelRoutePlanner/1.0')
CACHES = LocMemCache
```

### Step 3: Data Model
Generate: `apps/trip/models.py`, `apps/trip/admin.py`, `apps/trip/apps.py`

Model: `FuelStation` with fields:
- `opis_id` (CharField, unique)
- `name` (CharField)
- `address` (CharField)
- `city` (CharField)
- `state` (CharField, max_length=2)
- `rack_id` (CharField, blank=True)
- `price` (FloatField) ← cheapest price per station
- `lat` (FloatField, null=True)
- `lon` (FloatField, null=True)
- `geocode_failed` (BooleanField, default=False)

`apps.py` must call `station_loader.load_stations_into_memory()` inside `TripConfig.ready()`.

### Step 4: Management Commands
Generate: `apps/trip/management/commands/load_stations.py`

This command:
1. Reads `data/fuel-prices.csv` relative to BASE_DIR
2. Filters rows where State is a valid US state code (provide the full list of 50 state abbreviations)
3. Groups rows by `OPIS Truckstop ID`, keeps the row with minimum `Retail Price`
4. Uses `FuelStation.objects.update_or_create(opis_id=...)` for each station
5. Sets `lat=None`, `lon=None`, `geocode_failed=False` on create
6. Does NOT overwrite `lat`/`lon` on update if they are already set
7. Prints progress to `self.stdout` every 500 records
8. Prints final count: "Created X, Updated Y, Total Z stations."

Generate: `apps/trip/management/commands/geocode_stations.py`

This command:
1. Accepts `--limit N` and `--resume` arguments
2. Queries `FuelStation.objects.filter(geocode_failed=False, lat__isnull=True)`
3. Groups by unique `(city, state)` pairs
4. For each unique combo:
   a. Calls `geocoding.geocode_city_state(city, state)` from services
   b. Sleeps `time.sleep(1.0)` between EVERY Nominatim call (required by their ToS)
   c. If result: `FuelStation.objects.filter(city=city, state=state).update(lat=lat, lon=lon)`
   d. If no result: `FuelStation.objects.filter(city=city, state=state).update(geocode_failed=True)`
   e. Prints: "✓ Phoenix, AZ → (33.448, -112.073)" or "✗ Failed: UnknownCity, XX"
5. At end: prints "Geocoded: X/Y. Failed: Z. Remaining: W."
6. With `--resume`: skip combos where any station already has lat set
7. With `--limit N`: stop after N unique combos (for testing)

### Step 5: Services Layer
Generate each service file independently. Test each before moving to next.

**Generate: `apps/trip/services/station_loader.py`**

```python
# Module-level cache
_STATION_CACHE: list[dict] = []

def load_stations_into_memory() -> None:
    # Queries FuelStation WHERE lat IS NOT NULL AND geocode_failed = False
    # Populates _STATION_CACHE with dicts: {opis_id, name, address, city, state, lat, lon, price}
    # Logs: "Loaded {N} fuel stations into memory."

def get_all_stations() -> list[dict]:
    # Returns _STATION_CACHE

def get_station_count() -> int:
    # Returns len(_STATION_CACHE)
```

**Generate: `apps/trip/services/geocoding.py`**

```python
class GeocodingError(Exception):
    pass

def geocode_location(location_str: str) -> tuple[float, float] | None:
    # Calls Nominatim with q=location_str, format=json, limit=1, countrycodes=us
    # Sets User-Agent header from settings.NOMINATIM_USER_AGENT
    # Timeout: 10 seconds
    # Returns (float(lat), float(lon)) if found, None if not found
    # Raises GeocodingError on network/HTTP error
    # Does NOT sleep (single call for user input)

def geocode_city_state(city: str, state: str) -> tuple[float, float] | None:
    # Same as geocode_location but constructs query as "{city}, {state}, USA"
    # Returns (lat, lon) or None
    # Raises GeocodingError on network error
    # NOTE: Caller must sleep(1) between calls (not this function's responsibility)
```

**Generate: `apps/trip/services/routing.py`**

```python
from dataclasses import dataclass
import requests
from math import radians, sin, cos, sqrt, atan2
from django.conf import settings
from apps.trip.services.optimizer import haversine_miles  # reuse, don't reimplement

@dataclass
class RouteResult:
    polyline: list[list[float]]         # [[lon, lat], ...] — OSRM order
    total_distance_miles: float
    duration_hours: float
    cumulative_distances: list[float]   # mile marker at each polyline point

class RoutingError(Exception):
    pass

def get_route(start_lat, start_lon, finish_lat, finish_lon) -> RouteResult:
    # URL: {OSRM_BASE_URL}/route/v1/driving/{start_lon},{start_lat};{finish_lon},{finish_lat}
    # NOTE: OSRM uses lon,lat order in URL
    # Params: overview=full, geometries=geojson, steps=false
    # Timeout: 30 seconds (routing can be slow)
    # Parses response: routes[0].geometry.coordinates, routes[0].distance, routes[0].duration
    # Converts distance from meters to miles
    # Converts duration from seconds to hours
    # Calls compute_cumulative_distances(polyline) to build mile markers
    # Returns RouteResult
    # Raises RoutingError on any failure

def compute_cumulative_distances(polyline: list[list[float]]) -> list[float]:
    # polyline is [[lon, lat], ...] (OSRM order)
    # For each pair of adjacent points, compute haversine_miles
    # Build running sum starting at 0.0
    # cumulative_distances[0] = 0.0
    # cumulative_distances[i] = cumulative_distances[i-1] + haversine_miles(point[i-1], point[i])
    # Returns list of floats, same length as polyline
    # NOTE: haversine_miles takes (lat1, lon1, lat2, lon2) — swap from OSRM [lon, lat] order
```

**Generate: `apps/trip/services/optimizer.py`**

This is the most critical service. Generate with full implementation (not pseudocode).

```python
from math import radians, sin, cos, sqrt, atan2
from dataclasses import dataclass
from django.conf import settings

EARTH_RADIUS_MILES = 3958.8

@dataclass
class StationOnRoute:
    opis_id: str
    name: str
    address: str
    city: str
    state: str
    lat: float
    lon: float
    price: float
    route_mile: float
    deviation_miles: float

@dataclass
class FuelStop:
    order: int
    station: StationOnRoute
    gallons_to_fill: float
    cost_at_stop: float
    fuel_level_after: float

class InfeasibleRouteError(Exception):
    def __init__(self, stuck_at_mile: float):
        self.stuck_at_mile = stuck_at_mile
        super().__init__(f"No fuel station within 500 miles after mile {stuck_at_mile:.0f}")

def haversine_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Haversine formula. Only implementation in codebase. Import from here, never re-implement.
    """
    R = EARTH_RADIUS_MILES
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return R * 2 * atan2(sqrt(a), sqrt(1 - a))

def filter_stations_near_route(
    all_stations: list[dict],
    polyline: list[list[float]],
    cumulative_distances: list[float],
    off_route_threshold_miles: float = 50.0,
) -> list[StationOnRoute]:
    """
    1. Compute bounding box: min/max lat/lon from polyline + 2-degree buffer
    2. Pre-filter: exclude stations outside bounding box (no trig needed)
    3. For each station inside bbox:
       a. Find index of nearest polyline point (iterate all points, track min distance)
       b. deviation_miles = haversine_miles(station_lat, station_lon, nearest_lat, nearest_lon)
       c. route_mile = cumulative_distances[nearest_index]
    4. Keep only stations where deviation_miles <= off_route_threshold_miles
    5. Sort by route_mile ascending
    6. Return list of StationOnRoute
    
    IMPORTANT: polyline is [[lon, lat], ...] — swap to (lat, lon) when calling haversine_miles
    """

def select_optimal_stops(
    stations_on_route: list[StationOnRoute],
    total_distance_miles: float,
    tank_miles: float = 500.0,
    mpg: float = 10.0,
) -> list[FuelStop]:
    """
    GREEDY LOOK-AHEAD ALGORITHM — full implementation required:
    
    Initialize:
      current_mile = 0.0
      current_fuel_miles = tank_miles  # start full
      fuel_stops = []
    
    Loop while (current_mile + current_fuel_miles) < total_distance_miles:
      
      reachable = stations where current_mile < s.route_mile <= current_mile + current_fuel_miles
      
      if not reachable:
          raise InfeasibleRouteError(current_mile)
      
      full_window = stations where current_mile < s.route_mile <= current_mile + tank_miles
      
      cheapest_in_window = min(full_window, key=price)
      
      if cheapest_in_window reachable with current fuel:
          target = cheapest_in_window
      else:
          target = min(reachable, key=price)  # can't reach cheapest, pick best reachable
      
      # Travel to target
      miles_traveled = target.route_mile - current_mile
      current_fuel_miles -= miles_traveled
      current_mile = target.route_mile
      
      # How much to fill?
      next_window = stations where current_mile < s.route_mile <= current_mile + tank_miles
      
      if not next_window:
          fill_miles = tank_miles - current_fuel_miles  # fill completely (end of road)
      else:
          cheaper_ahead = [s for s in next_window if s.price < target.price]
          if not cheaper_ahead:
              fill_miles = tank_miles - current_fuel_miles  # fill completely, cheapest around
          else:
              nearest_cheaper = min(cheaper_ahead, key=lambda s: s.route_mile)
              # Buy just enough + 10-mile safety buffer
              needed_additional = nearest_cheaper.route_mile - current_mile - current_fuel_miles + 10
              fill_miles = max(0.0, min(needed_additional, tank_miles - current_fuel_miles))
              
              # Safety: ensure we can at least reach SOME station or the destination
              if current_fuel_miles + fill_miles < (nearest_cheaper.route_mile - current_mile):
                  fill_miles = nearest_cheaper.route_mile - current_mile - current_fuel_miles + 10
      
      gallons = round(fill_miles / mpg, 2)
      cost = round(gallons * target.price, 2)
      current_fuel_miles = round(current_fuel_miles + fill_miles, 2)
      
      fuel_stops.append(FuelStop(
          order=len(fuel_stops) + 1,
          station=target,
          gallons_to_fill=gallons,
          cost_at_stop=cost,
          fuel_level_after=current_fuel_miles,
      ))
    
    return fuel_stops
```

### Step 6: View, Serializer, URLs
Generate: `apps/trip/serializers.py`, `apps/trip/views.py`, `apps/trip/urls.py`, `config/urls.py`

**`TripPlanView` orchestration sequence (implement exactly this order):**
1. Validate with `TripRequestSerializer`
2. `geocode_location(start)` → `(start_lat, start_lon)` or return 400
3. `geocode_location(finish)` → `(finish_lat, finish_lon)` or return 400
4. Build `cache_key = _build_cache_key(start_lat, start_lon, finish_lat, finish_lon)`
5. `cached = cache.get(cache_key)` → if cached, use it; else call `get_route(...)` and `cache.set(key, route_result, TTL)`
6. `all_stations = get_all_stations()`
7. `stations_on_route = filter_stations_near_route(all_stations, route.polyline, route.cumulative_distances)`
8. `fuel_stops = select_optimal_stops(stations_on_route, route.total_distance_miles)`
9. Return `_build_response(...)` with status 200

**Cache key function:**
```python
import hashlib
def _build_cache_key(start_lat, start_lon, finish_lat, finish_lon) -> str:
    key_str = f"{start_lat:.4f},{start_lon:.4f},{finish_lat:.4f},{finish_lon:.4f}"
    return f"route:{hashlib.md5(key_str.encode()).hexdigest()}"
```

**Response builder — `_build_response()`:**
```python
def _build_response(route, fuel_stops, start_str, finish_str, start_coords, finish_coords) -> dict:
    total_gallons = round(sum(s.gallons_to_fill for s in fuel_stops), 2)
    total_cost = round(sum(s.cost_at_stop for s in fuel_stops), 2)
    prices = [s.station.price for s in fuel_stops]
    
    return {
        "route": {
            "start": start_str,
            "finish": finish_str,
            "start_coords": {"lat": start_coords[0], "lon": start_coords[1]},
            "finish_coords": {"lat": finish_coords[0], "lon": finish_coords[1]},
            "total_distance_miles": round(route.total_distance_miles, 1),
            "duration_hours": round(route.duration_hours, 1),
            "polyline": route.polyline,  # [[lon, lat], ...]
        },
        "fuel_stops": [
            {
                "order": stop.order,
                "station_name": stop.station.name,
                "address": stop.station.address,
                "city": stop.station.city,
                "state": stop.station.state,
                "lat": stop.station.lat,
                "lon": stop.station.lon,
                "price_per_gallon": round(stop.station.price, 3),
                "gallons_to_fill": stop.gallons_to_fill,
                "cost_at_stop": stop.cost_at_stop,
                "route_mile_marker": round(stop.station.route_mile, 1),
                "fuel_level_after_miles": stop.fuel_level_after,
            }
            for stop in fuel_stops
        ],
        "summary": {
            "total_stops": len(fuel_stops),
            "total_gallons": total_gallons,
            "total_fuel_cost": total_cost,
            "avg_price_per_gallon": round(total_cost / total_gallons, 3) if total_gallons > 0 else 0,
            "cheapest_stop_price": round(min(prices), 3) if prices else None,
            "most_expensive_stop_price": round(max(prices), 3) if prices else None,
        },
    }
```

### Step 7: README
Generate: `README.md`

Must include:
1. Project overview (2-3 sentences)
2. Setup instructions: `pip install -r requirements.txt`, `manage.py migrate`, `manage.py load_stations`, `manage.py geocode_stations` (with note about 64-minute runtime)
3. Run: `manage.py runserver`
4. Example Postman request (JSON body)
5. Example response (truncated polyline)
6. Notes on data limitations (CA coverage, geocoding accuracy)

---

## STRICT RULES FOR AI CODE GENERATOR

1. **Never create files not listed in the project structure above.**
2. **Never use `print()` in production code** — use `self.stdout.write()` in management commands and `import logging; logger = logging.getLogger(__name__)` in services.
3. **Never add `time.sleep()` inside a request handler (views.py).** Only in `geocode_stations.py`.
4. **OSRM URL uses lon,lat order** — never swap to lat,lon in the URL.
5. **haversine_miles is defined ONLY in optimizer.py** — routing.py imports it from there.
6. **All monetary values rounded to 2 decimal places.** All prices rounded to 3. All distances to 1.
7. **Every service function has a docstring.** Every model field has a comment explaining its purpose.
8. **The `_build_cache_key` and `_build_response` functions live in `views.py`**, not in services.
9. **`TripConfig.ready()` must guard against double-loading** with a check like `if not _STATION_CACHE:`.
10. **`load_stations` command must handle CSV rows where Retail Price is empty or non-numeric** — skip those rows with a warning.
11. **`RouteResult` cannot be JSON-serialized directly** (it's a dataclass). Cache the relevant fields as a plain dict, reconstruct RouteResult on cache hit.

---

## WHAT SUCCESS LOOKS LIKE

When Postman sends `POST /api/v1/trip/plan/` with:
```json
{"start": "New York, NY", "finish": "Los Angeles, CA"}
```

The response should:
- Return HTTP 200 in under 3 seconds (first call, OSRM cold)
- Return HTTP 200 in under 500ms (second call, OSRM cached)
- Contain 5-7 `fuel_stops` entries
- Show `total_fuel_cost` between $750 and $1,050
- Show `total_distance_miles` between 2,700 and 2,900
- Each stop has `route_mile_marker` increasing from first to last stop
- No stop is more than 500 miles from the previous stop
- The polyline contains at minimum 100 coordinate pairs

---

## MODULE GENERATION PROMPT TEMPLATES

Use these as prefix prompts when generating each module:

**For services:**
> "Generate `apps/trip/services/{filename}.py` following CODING_RULES.md strictly.
> This service is part of a layered Django architecture — no model imports, no view imports.
> Import haversine_miles from optimizer.py, not re-implemented here.
> Every function has a type-annotated signature and a docstring.
> Raise custom exception classes on failure, never return None for error conditions.
> Do not add any function or class not specified in ARCHITECTURE.md."

**For management commands:**
> "Generate `apps/trip/management/commands/{filename}.py` as a Django management command.
> The command is idempotent (safe to run multiple times).
> Progress is written to self.stdout. Errors per-item are warnings, not fatal.
> Do not stop the command on a single failed geocode — log and continue.
> The command reads/writes FuelStation model only."

**For views:**
> "Generate `apps/trip/views.py` following CODING_RULES.md.
> The view is a thin orchestrator — zero business logic here.
> All computation happens in the services layer.
> Every exception from a service is caught and mapped to a specific HTTP status code.
> The view has no direct imports from requests, math, or csv — only service imports."
