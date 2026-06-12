import logging
from dataclasses import dataclass
from math import radians, sin, cos, sqrt, atan2

from django.conf import settings

logger = logging.getLogger(__name__)

EARTH_RADIUS_MILES = 3958.8


# ── Data structures ──────────────────────────────────────────────────────────

@dataclass
class StationOnRoute:
    """A fuel station that has been projected onto the driving route."""
    opis_id:          str
    name:             str
    address:          str
    city:             str
    state:            str
    lat:              float
    lon:              float
    price:            float
    route_mile:       float   # Distance along route from start to the nearest route point
    deviation_miles:  float   # Perpendicular distance from route to this station


@dataclass
class FuelStop:
    """A chosen fuel stop with purchase decision details."""
    order:              int
    station:            StationOnRoute
    gallons_to_fill:    float
    cost_at_stop:       float
    fuel_level_after:   float  # Remaining range in miles after filling up here


class InfeasibleRouteError(Exception):
    """Raised when no fuel station is reachable before the tank runs empty."""
    def __init__(self, stuck_at_mile: float):
        self.stuck_at_mile = stuck_at_mile
        super().__init__(
            f"No fuel station reachable within 500 miles after mile {stuck_at_mile:.0f}. "
            f"Route cannot be completed with available stations."
        )


# ── Core math ────────────────────────────────────────────────────────────────

def haversine_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calculate great-circle distance between two points in miles.
    This is the ONLY haversine implementation in the codebase.
    All other modules MUST import this function — never re-implement it.

    Args:
        lat1, lon1: First point coordinates in decimal degrees
        lat2, lon2: Second point coordinates in decimal degrees

    Returns:
        Distance in miles (float)
    """
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = (
        sin(dlat / 2) ** 2
        + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    )
    return EARTH_RADIUS_MILES * 2 * atan2(sqrt(a), sqrt(1 - a))


# ── Route filtering ──────────────────────────────────────────────────────────

def filter_stations_near_route(
    all_stations: list[dict],
    polyline: list[list[float]],
    cumulative_distances: list[float],
    off_route_threshold_miles: float = 50.0,
) -> list[StationOnRoute]:
    """
    Filter the global station list down to only those near the driving route.

    Algorithm:
    1. Bounding box pre-filter: compute min/max lat+lon from polyline with a 2-degree
       buffer, then reject all stations outside this box using only comparisons (no trig).
       This eliminates ~70-80% of stations instantly.
    2. For each station that passed the bounding box:
       - Iterate all polyline points to find the nearest one (haversine)
       - Record the nearest point's cumulative distance as route_mile
       - Record the actual deviation distance from station to nearest route point
    3. Keep only stations where deviation_miles <= off_route_threshold_miles
    4. Sort surviving stations by route_mile ascending

    Args:
        all_stations: Full list of station dicts from in-memory cache
                      Each dict has: opis_id, name, address, city, state, lat, lon, price
        polyline: List of [lon, lat] pairs from OSRM (NOTE: OSRM uses lon,lat order)
        cumulative_distances: List of mile markers at each polyline point (same length as polyline)
        off_route_threshold_miles: Maximum deviation from route to include a station

    Returns:
        List of StationOnRoute, sorted by route_mile ascending
    """
    if not polyline or not all_stations:
        return []

    # Step 1: Build bounding box from polyline (polyline is [lon, lat] pairs)
    lats = [point[1] for point in polyline]
    lons = [point[0] for point in polyline]
    buffer = 2.0  # ~140 miles buffer, generous enough to catch all 50-mile deviations
    min_lat = min(lats) - buffer
    max_lat = max(lats) + buffer
    min_lon = min(lons) - buffer
    max_lon = max(lons) + buffer

    stations_on_route: list[StationOnRoute] = []

    for station in all_stations:
        s_lat = station['lat']
        s_lon = station['lon']

        # Step 2: Bounding box check — no trig needed, pure comparison
        if not (min_lat <= s_lat <= max_lat and min_lon <= s_lon <= max_lon):
            continue

        # Step 3: Find nearest polyline point using haversine
        min_dev = float('inf')
        best_route_mile = 0.0

        for i, (p_lon, p_lat) in enumerate(polyline):
            # NOTE: polyline is [lon, lat] — must swap to (lat, lon) for haversine
            dev = haversine_miles(s_lat, s_lon, p_lat, p_lon)
            if dev < min_dev:
                min_dev = dev
                best_route_mile = cumulative_distances[i]

        # Step 4: Threshold filter
        if min_dev <= off_route_threshold_miles:
            stations_on_route.append(StationOnRoute(
                opis_id=station['opis_id'],
                name=station['name'],
                address=station['address'],
                city=station['city'],
                state=station['state'],
                lat=s_lat,
                lon=s_lon,
                price=station['price'],
                route_mile=best_route_mile,
                deviation_miles=min_dev,
            ))

    # Step 5: Sort by position along route
    stations_on_route.sort(key=lambda s: s.route_mile)

    logger.debug(
        f"Filtered {len(all_stations)} total stations → "
        f"{len(stations_on_route)} stations within {off_route_threshold_miles} miles of route"
    )
    return stations_on_route


# ── Fuel optimization algorithm ───────────────────────────────────────────────

def select_optimal_stops(
    stations_on_route: list[StationOnRoute],
    total_distance_miles: float,
    tank_miles: float = 500.0,
    mpg: float = 10.0,
) -> list[FuelStop]:
    """
    Greedy look-ahead algorithm to select the cheapest fuel stops.

    Core logic at each decision point:
    - Look ahead up to a full tank (500 miles) from current position
    - If the cheapest station in that window is reachable → go there
    - If not reachable → go to the cheapest station we CAN reach right now
    - At the chosen station:
        - If no cheaper station exists in the next 500 miles → fill up completely
        - If a cheaper station is ahead → buy just enough fuel to reach it (+10 mile buffer)

    Args:
        stations_on_route: Sorted list of StationOnRoute (ascending by route_mile)
        total_distance_miles: Total length of the driving route in miles
        tank_miles: Maximum range on a full tank (default 500)
        mpg: Fuel efficiency (default 10)

    Returns:
        List of FuelStop objects representing the chosen stops in order

    Raises:
        InfeasibleRouteError: If no station is reachable before the tank empties
    """
    fuel_stops: list[FuelStop] = []
    current_mile: float = 0.0
    current_fuel_miles: float = tank_miles  # Start with a full tank

    while (current_mile + current_fuel_miles) < total_distance_miles:

        # All stations reachable from current position with current fuel
        reachable = [
            s for s in stations_on_route
            if current_mile < s.route_mile <= current_mile + current_fuel_miles
        ]

        if not reachable:
            raise InfeasibleRouteError(current_mile)

        # All stations reachable if we had a FULL tank from current position
        full_window = [
            s for s in stations_on_route
            if current_mile < s.route_mile <= current_mile + tank_miles
        ]

        # Find cheapest in full window
        cheapest_in_window = min(full_window, key=lambda s: s.price)

        # Can we reach the cheapest station with our current (possibly partial) fuel?
        can_reach_cheapest = (
            cheapest_in_window.route_mile - current_mile
        ) <= current_fuel_miles

        target = cheapest_in_window if can_reach_cheapest else min(reachable, key=lambda s: s.price)

        # ── Travel to the target station ──────────────────────────────────────
        miles_traveled = target.route_mile - current_mile
        current_fuel_miles -= miles_traveled
        current_mile = target.route_mile

        # ── Decide how much to fill ───────────────────────────────────────────
        # Look ahead from this station: any cheaper options in the next full tank?
        next_window = [
            s for s in stations_on_route
            if current_mile < s.route_mile <= current_mile + tank_miles
        ]

        if not next_window:
            # No more stations ahead — fill up completely to guarantee we reach the end
            fill_miles = tank_miles - current_fuel_miles

        else:
            cheaper_ahead = [s for s in next_window if s.price < target.price]

            if not cheaper_ahead:
                # This station is the cheapest in the next 500 miles → fill completely
                fill_miles = tank_miles - current_fuel_miles

            else:
                # A cheaper station exists ahead → buy only what we need to reach it
                nearest_cheaper = min(cheaper_ahead, key=lambda s: s.route_mile)
                miles_to_next_cheap = nearest_cheaper.route_mile - current_mile

                # Additional fuel needed to reach cheaper station + 10-mile safety buffer
                needed_extra = miles_to_next_cheap - current_fuel_miles + 10.0
                fill_miles = max(0.0, min(needed_extra, tank_miles - current_fuel_miles))

                # Final safety check: ensure we can definitely reach at least one more station
                if current_fuel_miles + fill_miles < miles_to_next_cheap:
                    fill_miles = miles_to_next_cheap - current_fuel_miles + 10.0
                    fill_miles = min(fill_miles, tank_miles - current_fuel_miles)

        gallons_to_fill = round(fill_miles / mpg, 2)
        cost_at_stop    = round(gallons_to_fill * target.price, 2)
        current_fuel_miles = round(current_fuel_miles + fill_miles, 2)

        fuel_stops.append(FuelStop(
            order=len(fuel_stops) + 1,
            station=target,
            gallons_to_fill=gallons_to_fill,
            cost_at_stop=cost_at_stop,
            fuel_level_after=round(current_fuel_miles, 1),
        ))

    return fuel_stops
