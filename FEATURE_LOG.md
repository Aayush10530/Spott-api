# FEATURE_LOG.md
# Fuel Route Planner — Feature & Decision Log

> Every feature, architectural decision, fix, and change is tracked here.
> AI agents: Read this before generating code. Understand what's been decided and why.
> Update this file after every significant change.

---

## Project Initialization

**Date:** Project Start
**Status:** Planning complete, ready to build

### Architectural Decisions Made (ADRs)

---

#### ADR-001: Use OSRM for Routing (not Google Maps, MapBox, or OpenRouteService)

**Decision:** Use OSRM public demo server (`router.project-osrm.org`)

**Rationale:**
- Completely free, no API key required
- Returns full route geometry (GeoJSON) in a single call
- Satisfies the "1 routing API call" requirement explicitly
- No signup, no credit card, no rate limit worries for demo
- Competitors: OpenRouteService requires signup; Google Maps costs money; HERE maps requires credit card

**Trade-off accepted:** OSRM public server is for demo/testing. In production, we'd self-host or use ORS. Fine for assessment.

---

#### ADR-002: Use Nominatim for Geocoding (not Google Geocoding API)

**Decision:** Use Nominatim OpenStreetMap geocoding

**Rationale:**
- Free, no API key
- Sufficient accuracy for city-level geocoding
- Works for all US cities

**Trade-off accepted:** 1 req/sec rate limit makes batch geocoding slow (~64 min). This is a one-time setup cost. Per-request geocoding (2 calls for start/finish) is fine.

**Note:** Nominatim geocoding calls do NOT count toward the "routing API call" limit in the assessment requirements. They are separate concerns.

---

#### ADR-003: Pre-geocode Stations Offline (not live per request)

**Decision:** Run `geocode_stations` management command once before first use. Store lat/lon in DB.

**Rationale:**
- 3,813 unique city+state combos × 1 req/sec = 64 minutes
- Completely unacceptable for per-request geocoding
- One-time cost paid at setup → zero cost at request time
- Stations don't change (static CSV)

**Implementation:** `manage.py geocode_stations` with `--resume` flag for fault tolerance.

---

#### ADR-004: Load Stations Into Memory at Startup (not DB per request)

**Decision:** Use module-level `_STATION_CACHE` list populated in `TripConfig.ready()`

**Rationale:**
- 6,626 stations × ~150 bytes per dict ≈ ~1 MB RAM (trivial)
- Eliminates DB query on every request hot path
- With bounding box filter, processing is sub-100ms

**Alternative rejected:** Django cache (memcached/Redis) would require extra infrastructure. In-memory is simpler and equally fast for single-process demo server.

---

#### ADR-005: Greedy Look-Ahead Algorithm (not Dynamic Programming)

**Decision:** Implement greedy look-ahead algorithm for fuel stop optimization

**Rationale:**
- True optimal solution (DP) is significantly more complex to implement and explain
- Greedy look-ahead produces results within 2-5% of optimal
- Easy to explain in a 5-minute Loom video
- O(n²) time complexity — fast enough for 50-500 stations on a route

**Algorithm summary:**
At each decision point:
1. Find cheapest station within full tank range (500 miles)
2. Travel to it
3. At that station, look ahead: is there a cheaper station in the next 500 miles?
4. If yes: buy only enough to reach it
5. If no: fill up completely

---

#### ADR-006: Deduplication by Minimum Price per OPIS ID

**Decision:** When OPIS Truckstop ID has multiple price entries (different fuel grades), keep the row with the minimum Retail Price.

**Rationale:**
- Multiple prices = multiple fuel grades (regular, diesel, premium)
- Vehicle type not specified in requirements → use cheapest available
- Simple, deterministic rule

---

#### ADR-007: Off-Route Threshold of 50 Miles

**Decision:** Include fuel stations within 50 miles of the route, exclude everything beyond

**Rationale:**
- Interstate highway exits typically within 1-5 miles of the interstate
- 50-mile threshold is generous enough to capture all realistic truck stops
- Larger threshold → more false positives → slower algorithm
- Smaller threshold (e.g., 10 miles) → might miss valid stations in rural areas

---

#### ADR-008: Bounding Box Pre-filter Before Haversine

**Decision:** Filter stations by bounding box (with 2-degree buffer) before computing haversine distance

**Rationale:**
- Bounding box check = 4 comparisons (no trig) = extremely fast
- Eliminates ~70-80% of irrelevant stations instantly
- Haversine only runs on stations inside the bounding box
- Makes the route-filter step sub-100ms even for long routes

---

#### ADR-009: SQLite as Database

**Decision:** Use SQLite (Django default)

**Rationale:**
- Assessment does not require PostgreSQL
- No external database setup required
- FuelStation table is read-mostly (written once during setup, read at startup)
- 6,626 rows is trivial for SQLite

---

#### ADR-010: Cache OSRM Responses (1-hour TTL)

**Decision:** Cache OSRM route results in Django LocMemCache keyed on hashed coordinates

**Rationale:**
- Repeated calls with same start/finish (e.g., Postman demo) should not re-hit OSRM
- 1-hour TTL is reasonable (routes don't change)
- Key = MD5 of "{lat:.4f},{lon:.4f},{lat:.4f},{lon:.4f}" — deterministic, short

---

### Features To Build (Backlog)

**Phase 1 — Core (Must complete)**

- [ ] F-001: Django project scaffold (`config/`, `apps/trip/`)
- [ ] F-002: `FuelStation` model with all fields
- [ ] F-003: `load_stations` management command (CSV → DB)
- [ ] F-004: `geocode_stations` management command (batch Nominatim)
- [ ] F-005: `station_loader` service (in-memory cache, TripConfig.ready)
- [ ] F-006: `geocoding` service (Nominatim wrapper, per-request)
- [ ] F-007: `routing` service (OSRM single call + cumulative distances)
- [ ] F-008: `optimizer` service (haversine + filter_near_route + select_optimal_stops)
- [ ] F-009: `TripRequestSerializer` (input validation)
- [ ] F-010: `TripPlanView` (orchestration, error handling, cache, response building)
- [ ] F-011: URL routing (`/api/v1/trip/plan/`)
- [ ] F-012: Settings and .env setup
- [ ] F-013: requirements.txt

**Phase 2 — Quality (Complete before Loom recording)**

- [ ] F-014: End-to-end test with Postman (NY → LA, Chicago → Miami, Seattle → Houston)
- [ ] F-015: README with setup instructions and example Postman request
- [ ] F-016: Verify response time < 2 seconds (after OSRM cache warms up)

---

### Change Log

| Version | Change | Reason |
|---------|--------|--------|
| v0.1 | Initial documentation | Project start |

---

### Known Issues / Risks

| ID | Risk | Mitigation |
|----|------|-----------|
| R-001 | OSRM public server could be slow | Cache routes. Demo shows cached speed. |
| R-002 | Nominatim batch geocoding takes 64 min | One-time setup. Document in README. |
| R-003 | CA only has 8 stations in CSV | Document as data limitation, not a bug |
| R-004 | Geocoding fails for some city+state combos | Mark as geocode_failed=True, skip gracefully |
| R-005 | Route through area with no stations | Return 400 with helpful message |

---

### Testing Checklist (Pre-Loom)

- [ ] `POST /api/v1/trip/plan/` with `{"start": "New York, NY", "finish": "Los Angeles, CA"}`
  - Expected: 6+ fuel stops, total cost ~$800-950
- [ ] Short route: `{"start": "Chicago, IL", "finish": "Indianapolis, IN"}` (~180 miles)
  - Expected: 0 fuel stops (within 500-mile tank), cost = total gallons × cheapest en-route price
- [ ] Invalid location: `{"start": "Fakeville, ZZ", "finish": "Los Angeles, CA"}`
  - Expected: 400 error "Could not geocode..."
- [ ] Missing field: `{"start": "New York, NY"}`
  - Expected: 400 validation error
- [ ] Same start/finish: `{"start": "Dallas, TX", "finish": "Dallas, TX"}`
  - Expected: 400 "Start and finish must be different"
- [ ] Second call same route: verify response is faster (cache hit)
