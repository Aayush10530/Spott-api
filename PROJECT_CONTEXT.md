# PROJECT_CONTEXT.md
# Fuel Route Planner — Project Memory

> **Last Updated:** Initial Setup
> **Status:** In Development
> **Assignment:** Spotter AI — Remote Backend Django Engineer Assessment

---

## What This Project Is

A Django REST API that accepts a start and finish location (both within the USA), computes the optimal driving route, identifies the most cost-effective fuel stops along the way, and returns the full route geometry along with a detailed fuel cost breakdown.

This is a **single-endpoint backend API** — no frontend. The evaluator will test it via Postman.

---

## Business Rules (Non-Negotiable)

| Rule | Value |
|------|-------|
| Vehicle max range | 500 miles per full tank |
| Fuel efficiency | 10 miles per gallon (MPG) |
| Tank capacity | 50 gallons (500 miles ÷ 10 MPG) |
| Vehicle starts | With a full tank |
| Fuel price source | `data/fuel-prices.csv` (OPIS dataset — static, pre-loaded) |
| Location scope | USA only |
| Optimization goal | Minimize total fuel cost (price-based greedy) |
| Off-route threshold | Stations within 50 miles of route are eligible |

---

## Data Source Analysis (fuel-prices.csv)

### Raw CSV Structure
```
OPIS Truckstop ID | Truckstop Name | Address | City | State | Rack ID | Retail Price
```

### Key Findings
- **Total rows:** 8,151
- **US-only rows:** 7,531 (non-US states like AB, BC, ON etc. are filtered out)
- **Unique stations after dedup by OPIS ID:** 6,626
- **Unique city+state combos (for geocoding):** 3,813
- **Price range:** $2.687 – $6.399 per gallon
- **Median price:** ~$3.39/gallon
- **NO latitude/longitude in CSV** — must be geocoded from City+State (this is the core data challenge)

### Deduplication Rule
Some OPIS station IDs appear multiple times (678 IDs have duplicates) — these represent different fuel grades (diesel, regular, premium). **Always keep the row with the minimum Retail Price per OPIS Truckstop ID.** This gives the cheapest available fuel at that station.

### State Coverage
- Best coverage: TX (776), IL (329), WI (295), GA (284), OH (262)
- Sparse coverage: RI (2), CA (8), DE (15), VT (16), NH (23)
- **CA having only 8 stations is a known data limitation** — routes through CA may have fewer options

---

## External APIs Used

### 1. OSRM — Open Source Routing Machine (PRIMARY: routing)
- **URL:** `http://router.project-osrm.org/route/v1/driving/{lon},{lat};{lon},{lat}`
- **Cost:** Completely free, no API key required
- **Rate limit:** Fair use (no hard limit stated, but keep calls minimal)
- **What it returns:** Full route geometry (GeoJSON LineString), total distance in meters, duration in seconds
- **CRITICAL:** OSRM uses `longitude,latitude` order (not lat,lon!)
- **Params to always include:** `overview=full&geometries=geojson&steps=false`
- **Usage in this project:** Called exactly ONCE per trip plan request
- **Fallback:** None needed — if OSRM is down, return 503

### 2. Nominatim — OpenStreetMap Geocoding (SECONDARY: geocoding)
- **URL:** `https://nominatim.openstreetmap.org/search`
- **Cost:** Free, no API key
- **Rate limit:** 1 request/second STRICTLY ENFORCED — must `time.sleep(1)` between calls
- **Required header:** `User-Agent: FuelRoutePlanner/1.0`
- **What it returns:** lat/lon for a location string
- **Usage in this project:**
  - (A) **One-time offline:** `geocode_stations` management command to pre-geocode all 3,813 city+state combos
  - (B) **Per request:** Geocode the user's start and finish location strings (~2 calls per request)
- **Note:** Does NOT count toward "routing API call limit" mentioned in requirements

---

## Tech Stack

| Layer | Technology | Version |
|-------|-----------|---------|
| Framework | Django | 5.2 (latest stable) |
| API Layer | Django REST Framework | 3.15.x |
| Database | SQLite | Default (no external DB needed) |
| HTTP Client | requests | 2.31.x |
| Environment | python-dotenv | 1.0.x |
| Python | Python | 3.11+ |

**No additional geo libraries needed.** Haversine distance is implemented in pure Python using `math` module. No PostGIS, GeoDjango, or shapely required.

---

## Core User Flow (Per Request)

```
POST /api/v1/trip/plan/
  Body: { "start": "New York, NY", "finish": "Los Angeles, CA" }

Step 1: Validate input (both fields required, non-empty strings)

Step 2: Geocode start location via Nominatim
  → (start_lat, start_lon)

Step 3: Geocode finish location via Nominatim
  → (finish_lat, finish_lon)

Step 4: Check cache (start_coords + finish_coords hash)
  → HIT: skip to Step 7
  → MISS: continue

Step 5: Call OSRM routing API (SINGLE CALL)
  → route_polyline (list of [lon,lat] coords)
  → total_distance_meters → convert to miles

Step 6: Store OSRM result in cache (TTL: 1 hour)

Step 7: Filter fuel stations from in-memory cache
  → Bounding box pre-filter (eliminates ~80% of stations fast)
  → Haversine distance per remaining station vs nearest route point
  → Keep stations within 50 miles of route
  → Assign each station a "route_mile" (distance from route start to nearest route point)
  → Sort stations by route_mile

Step 8: Run fuel optimization algorithm
  → Input: sorted on-route stations, total distance, start full tank
  → Output: list of chosen stops with gallons to buy + cost at each stop

Step 9: Build and return response
  → route geometry, fuel stops array, total cost summary
```

---

## Data Setup Flow (One-Time, Before Running Server)

```
1. python manage.py load_stations
   → Reads fuel-prices.csv
   → Filters US-only (valid US state codes)
   → Deduplicates by OPIS ID (keep min price)
   → Saves 6,626 FuelStation records to SQLite (without lat/lon yet)

2. python manage.py geocode_stations
   → Groups stations by unique city+state (3,813 combos)
   → For each combo: calls Nominatim, sleeps 1 second
   → Runtime: ~64 minutes (one-time only!)
   → Updates FuelStation records with lat/lon
   → Uses resume capability (skips already-geocoded stations)
   → Stations that fail geocoding: marked as geocode_failed=True, skipped silently

3. python manage.py runserver
   → On startup (AppConfig.ready): loads all geocoded stations into memory
   → Stations without lat/lon (geocode_failed) are excluded from the in-memory cache
```

---

## API Contract

### Request
```
POST /api/v1/trip/plan/
Content-Type: application/json

{
  "start": "New York, NY",          // required, string, US location
  "finish": "Los Angeles, CA"        // required, string, US location
}
```

### Success Response (200 OK)
```json
{
  "route": {
    "start": "New York, NY",
    "finish": "Los Angeles, CA",
    "start_coords": { "lat": 40.7128, "lon": -74.0060 },
    "finish_coords": { "lat": 34.0522, "lon": -118.2437 },
    "total_distance_miles": 2789.5,
    "duration_hours": 40.2,
    "polyline": [
      [-74.0060, 40.7128],
      [-74.2000, 40.6500],
      "... more [lon, lat] pairs ..."
    ]
  },
  "fuel_stops": [
    {
      "order": 1,
      "station_name": "LOVES TRAVEL STOP #766",
      "address": "I-80, EXIT 27",
      "city": "Atkinson",
      "state": "IL",
      "lat": 41.4150,
      "lon": -89.9800,
      "price_per_gallon": 3.389,
      "gallons_to_fill": 32.5,
      "cost_at_stop": 110.14,
      "route_mile_marker": 782.3,
      "miles_remaining_after_fill": 500.0
    }
  ],
  "summary": {
    "total_stops": 6,
    "total_gallons": 278.9,
    "total_fuel_cost": 892.45,
    "avg_price_per_gallon": 3.20,
    "most_expensive_stop": 3.85,
    "cheapest_stop": 2.95
  }
}
```

### Error Responses
```json
// 400 — Bad input
{ "error": "Both 'start' and 'finish' fields are required." }

// 400 — Location not found
{ "error": "Could not geocode location: 'XYZ City, ZZ'. Please use a valid US city and state." }

// 400 — Route infeasible (gap in stations)
{ "error": "No fuel station found within 500 miles after mile 340. Route is not feasible with available stations." }

// 503 — Routing API down
{ "error": "Routing service unavailable. Please try again later." }
```

---

## In-Memory Station Cache Strategy

Loaded once in `TripConfig.ready()` (apps.py):

```python
STATION_CACHE = []  # module-level list, populated at startup

# Each entry is a dict:
{
  "opis_id": "135",
  "name": "LOVES TRAVEL STOP #766",
  "address": "I-80, EXIT 27",
  "city": "Atkinson",
  "state": "IL",
  "lat": 41.415,
  "lon": -89.980,
  "price": 3.389
}
```

**Why in-memory:** Avoids DB round-trips during request. 6,626 stations × ~150 bytes = ~1 MB. Trivial memory footprint.

---

## Sample Route Calculations

| Route | Distance | Gallons | Est. Cost (avg $3.20) | Min Stops |
|-------|----------|---------|----------------------|-----------|
| New York → Los Angeles | 2,790 mi | 279 gal | ~$892 | 6 |
| Chicago → Miami | 1,380 mi | 138 gal | ~$441 | 3 |
| Seattle → Houston | 2,100 mi | 210 gal | ~$672 | 5 |
| Boston → Denver | 1,960 mi | 196 gal | ~$627 | 4 |
| Dallas → Atlanta | 780 mi | 78 gal | ~$250 | 2 |

---

## Known Limitations & Accepted Trade-offs

1. **CA has only 8 stations in dataset** — Routes heavily through CA may have limited stop options. Acceptable since it's a data limitation, not a code bug.
2. **Geocoding is city-level, not street-level** — Station coordinates are city centroid, not exact GPS. Accuracy is ±5 miles, acceptable for route planning.
3. **OSRM public demo server** — Not production-grade. Could be slow during high traffic. Acceptable for assessment demo.
4. **In-memory cache resets on restart** — Fine for demo. Would use Redis in production.
5. **Static fuel prices** — Real world prices change daily. The CSV is a fixed snapshot.
6. **Algorithm is greedy, not DP** — True optimal solution would use dynamic programming. Greedy look-ahead gives results within 2-5% of optimal and is far simpler. Acceptable.

---

## Project File Structure

```
fuel_route_planner/
├── .env                           # NOMINATIM_USER_AGENT, DEBUG, SECRET_KEY
├── .env.example                   # Template for env vars
├── .gitignore
├── requirements.txt
├── manage.py
├── README.md
├── data/
│   └── fuel-prices.csv            # Original CSV (DO NOT MODIFY)
├── config/                        # Django project config package
│   ├── __init__.py
│   ├── settings.py
│   ├── urls.py
│   └── wsgi.py
└── apps/
    └── trip/                      # Sole Django app
        ├── __init__.py
        ├── apps.py                # TripConfig: loads stations into memory on startup
        ├── admin.py               # FuelStation registered for visibility
        ├── models.py              # FuelStation model
        ├── serializers.py         # TripRequestSerializer, TripResponseSerializer
        ├── views.py               # TripPlanView (single APIView)
        ├── urls.py
        ├── services/
        │   ├── __init__.py
        │   ├── geocoding.py       # Nominatim wrapper
        │   ├── routing.py         # OSRM wrapper
        │   ├── optimizer.py       # Fuel stop selection algorithm
        │   └── station_loader.py  # In-memory cache management
        └── management/
            └── commands/
                ├── __init__.py
                ├── load_stations.py     # CSV → DB
                └── geocode_stations.py  # Batch geocode city+state → lat/lon
```
