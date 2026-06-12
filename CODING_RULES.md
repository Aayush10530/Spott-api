# CODING_RULES.md
# Fuel Route Planner — Coding Rules & Conventions

> AI code generators MUST follow every rule in this file without exception.
> These rules exist to prevent vibe-coded drift and keep the codebase production-quality.

---

## 0. The Prime Directives

1. **Generate modules, not entire startups.** Write exactly what is specified in ARCHITECTURE.md. Do not add new files, classes, or endpoints that weren't asked for.
2. **One coding style only.** No mixing of function-based views and class-based views. No mixing of `requests` and `httpx`. No mixing of f-strings and `.format()`.
3. **Reuse before creating.** Before writing new utility code, check if it already exists in `services/`. The `haversine_miles()` function must live in `optimizer.py` only — import from there, never re-implement.
4. **No business logic in views.** Views orchestrate. Services compute. Models store. Never blur these lines.
5. **Commit after every stable, tested feature.** Never commit broken code.

---

## 1. File & Directory Naming

| Type | Convention | Example |
|------|-----------|---------|
| Python files | `snake_case.py` | `station_loader.py` |
| Python packages | `snake_case/` with `__init__.py` | `services/` |
| Management commands | `snake_case.py` | `load_stations.py` |
| Markdown docs | `UPPER_SNAKE_CASE.md` | `PROJECT_CONTEXT.md` |
| CSV/data files | `kebab-case.csv` | `fuel-prices.csv` |
| Env file | `.env` | `.env` |

**Django app location:** All apps live under `apps/`. The trip app is `apps/trip/`, not `trip/` at root.

---

## 2. Python Naming

```python
# Classes: PascalCase
class FuelStation:          ✓
class fuelStation:          ✗
class fuel_station:         ✗

# Functions & methods: snake_case, verb-first
def get_route():            ✓
def filter_stations():      ✓
def route():                ✗ (too vague)
def filterStations():       ✗

# Variables: snake_case, descriptive
total_distance_miles = 2790.5     ✓
d = 2790.5                        ✗ (too short)
totalDistanceMiles = 2790.5       ✗ (camelCase)

# Constants: UPPER_SNAKE_CASE, defined in settings.py or top of module
EARTH_RADIUS_MILES = 3958.8       ✓
VEHICLE_TANK_MILES = 500          ✓ (in settings.py)
tank = 500                        ✗

# Type hints: always on function signatures, never inside function bodies
def haversine_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:  ✓
def haversine_miles(lat1, lon1, lat2, lon2):                                        ✗

# Exceptions: PascalCase ending in Error
class GeocodingError(Exception):      ✓
class geocoding_error(Exception):     ✗

# Dataclasses over plain dicts for structured return values
@dataclass
class RouteResult:                    ✓
return {"polyline": ..., "distance": ...}  ✗ (for complex return values)
```

---

## 3. Service Layer Rules

```python
# CORRECT: Services are standalone functions and classes, no Django imports at module level
# services/geocoding.py
import requests
from django.conf import settings   # OK — only conf, no models

def geocode_location(location_str: str) -> tuple[float, float] | None:
    ...

# WRONG: Services importing models directly
# services/geocoding.py
from apps.trip.models import FuelStation  # ✗ — never import models in services
```

```python
# CORRECT: Views import from services, not directly from external libs
# views.py
from apps.trip.services.geocoding import geocode_location, GeocodingError
from apps.trip.services.routing import get_route, RoutingError

# WRONG: Views calling requests directly
# views.py
import requests
response = requests.get("https://nominatim...")  # ✗ — belongs in service layer
```

---

## 4. Error Handling Rules

```python
# CORRECT: Explicit exception hierarchy, caught in views
# services/routing.py
class RoutingError(Exception):
    pass

def get_route(...) -> RouteResult:
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
    except requests.RequestException as e:
        raise RoutingError(f"OSRM request failed: {e}") from e
    
    data = resp.json()
    if data.get("code") != "Ok":
        raise RoutingError(f"OSRM returned error: {data.get('code')}")

# CORRECT: View catches specific exceptions, maps to HTTP status
# views.py
try:
    route_result = get_route(start_lat, start_lon, finish_lat, finish_lon)
except RoutingError:
    return Response(
        {"error": "Routing service unavailable. Please try again later."},
        status=status.HTTP_503_SERVICE_UNAVAILABLE
    )

# WRONG: Bare except, swallowed exceptions, generic 500s
try:
    route_result = get_route(...)
except:        # ✗ bare except
    pass       # ✗ swallowed
```

---

## 5. Django-Specific Rules

```python
# CORRECT: Use Django settings constants, never hardcode values
from django.conf import settings
tank_miles = settings.VEHICLE_TANK_MILES   ✓

# WRONG: Hardcoded magic numbers in business logic
if current_fuel < 500:   ✗
if distance > 50:        ✗

# CORRECT: Model fields have explicit types, no naked CharField
price = models.FloatField()                          ✓
lat = models.FloatField(null=True, blank=True)       ✓

# WRONG: String for numeric data
price = models.CharField(max_length=20)              ✗

# CORRECT: Use .values() when fetching for non-ORM purposes
stations = FuelStation.objects.filter(...).values('opis_id', 'name', 'lat', 'lon', 'price')  ✓

# WRONG: Fetch full model objects then access attributes (wastes memory)
stations = FuelStation.objects.filter(...)
for s in stations:
    s.lat  # ✗ — loads entire model including non-needed fields
```

---

## 6. DRF (Django REST Framework) Rules

```python
# CORRECT: Use APIView (not ViewSet — single endpoint doesn't need full CRUD)
class TripPlanView(APIView):
    def post(self, request):
        serializer = TripRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        ...

# WRONG: Using @api_view decorator (less structured for complex views)
@api_view(['POST'])
def trip_plan(request):   ✗

# CORRECT: Always use serializer for input validation, never raw request.data
validated = serializer.validated_data   ✓
raw = request.data['start']             ✗ (bypasses validation)

# CORRECT: Return Response() always, never JsonResponse or HttpResponse
return Response(data, status=status.HTTP_200_OK)    ✓
return JsonResponse(data)                           ✗
```

---

## 7. Algorithm / Math Rules

```python
# CORRECT: haversine_miles defined ONCE in optimizer.py, imported everywhere else
# optimizer.py
def haversine_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Standard haversine formula. Returns distance in miles."""
    R = 3958.8
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return R * 2 * atan2(sqrt(a), sqrt(1 - a))

# WRONG: Re-implementing haversine in routing.py, geocoding.py, etc.
# routing.py
def distance(p1, p2):   ✗ — import from optimizer instead
    ...

# CORRECT: Explicit unit labels in variable names
total_distance_miles = 2790.5     ✓
distance_meters = 4_491_234.5     ✓  (before conversion)
d = 2790.5                        ✗

# CORRECT: OSRM coordinates are [lon, lat] — always comment this
# OSRM returns [lon, lat] pairs — DO NOT swap these
for lon, lat in polyline:    ✓  # correct OSRM order
for lat, lon in polyline:    ✗  # will produce wrong distance calculations

# CORRECT: Round monetary values to 2 decimal places
cost = round(gallons * price, 2)   ✓
cost = gallons * price             ✗ (floating point noise in output)

# CORRECT: Round gallons to 2 decimal places, route miles to 1
gallons = round(fill_miles / mpg, 2)           ✓
route_mile = round(cumulative_distance, 1)     ✓
```

---

## 8. HTTP Client Rules

```python
# CORRECT: Always set timeout on requests
response = requests.get(url, timeout=10)    ✓
response = requests.get(url)               ✗ (can hang forever)

# CORRECT: Always set User-Agent for Nominatim
headers = {"User-Agent": settings.NOMINATIM_USER_AGENT}
response = requests.get(url, headers=headers, timeout=10)   ✓

# WRONG: No User-Agent on Nominatim (violates their terms of service)
response = requests.get(url, timeout=10)   ✗ (for Nominatim only)

# CORRECT: Check status code, raise for non-200
response.raise_for_status()   ✓

# CORRECT: Rate limit sleep in management command only, NOT in per-request code
# management/commands/geocode_stations.py
time.sleep(1.0)   ✓ (in management command batch loop)

# views.py
time.sleep(1.0)   ✗ (never sleep in a request handler)
```

---

## 9. Management Command Rules

```python
# CORRECT: Commands are idempotent (safe to run multiple times)
# load_stations.py should use update_or_create or bulk_create(update_conflicts=True)

# CORRECT: Commands print progress to self.stdout, not print()
self.stdout.write(f"Processed {count} stations.")             ✓
self.stdout.write(self.style.SUCCESS(f"Done: {count}"))      ✓
print(f"Done: {count}")                                        ✗

# CORRECT: Commands accept optional arguments
class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, default=None)
        parser.add_argument('--resume', action='store_true', default=False)

# CORRECT: Catch and log errors per-item, never abort entire command
for city, state in combos:
    try:
        result = geocode_city_state(city, state)
    except GeocodingError as e:
        self.stdout.write(self.style.WARNING(f"Failed {city}, {state}: {e}"))
        continue  ✓  # skip one bad item, continue with rest
```

---

## 10. Import Order

Follow PEP8 import order, enforced in every file:

```python
# 1. Standard library
import time
import hashlib
from math import radians, sin, cos, sqrt, atan2
from dataclasses import dataclass

# 2. Third-party
import requests
from rest_framework.views import APIView
from rest_framework.response import Response

# 3. Django
from django.conf import settings
from django.core.cache import cache

# 4. Local / project
from apps.trip.services.geocoding import geocode_location, GeocodingError
from apps.trip.services.routing import get_route, RoutingError
from apps.trip.services.optimizer import filter_stations_near_route, select_optimal_stops
```

---

## 11. Response Shape Rules

```python
# CORRECT: Consistent key naming — snake_case in all JSON responses
{"total_fuel_cost": 892.45, "fuel_stops": [...]}   ✓
{"totalFuelCost": 892.45, "fuelStops": [...]}       ✗ (camelCase is JS, not Python API)

# CORRECT: Error responses always use "error" key (singular)
{"error": "Could not geocode location."}    ✓
{"errors": ["..."]}                         ✗  (DRF default is fine for validation)
{"message": "Error occurred"}               ✗

# CORRECT: Numeric fields are numbers, not strings
{"price_per_gallon": 3.389}    ✓
{"price_per_gallon": "3.389"}  ✗
```

---

## 12. What NOT to Build

These are explicitly out of scope. Do NOT add them even if they seem helpful:

- ❌ No authentication / JWT / tokens
- ❌ No database of saved routes or trip history
- ❌ No frontend / HTML templates
- ❌ No WebSocket support
- ❌ No Celery / async tasks
- ❌ No Docker configuration
- ❌ No multiple endpoints (only `POST /api/v1/trip/plan/`)
- ❌ No fuel type selection (diesel vs gasoline) — use minimum price per station
- ❌ No `GET /api/v1/trip/plan/` handler — POST only
- ❌ No pagination on fuel stops list
- ❌ No external database (PostgreSQL, etc.) — SQLite only
