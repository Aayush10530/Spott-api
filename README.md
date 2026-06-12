# ⛽ Spotter Fuel Route Planner API

![Python](https://img.shields.io/badge/Python-3.10%2B-blue?style=for-the-badge&logo=python)
![Django](https://img.shields.io/badge/Django-5.0-092E20?style=for-the-badge&logo=django)
![REST API](https://img.shields.io/badge/API-RESTful-orange?style=for-the-badge)

A high-performance Django REST API that computes the optimal driving route between any two locations in the US, while strategically selecting the cheapest fuel stops along the way to minimize total fuel costs. 

---

## 🚀 Features

- **Intelligent Routing**: Leverages the OSRM (Open Source Routing Machine) API to generate highly accurate turn-by-turn geometry.
- **Cost Optimization Algorithm**: Calculates the cheapest fuel stops across a 500-mile vehicle tank range constraint to achieve the lowest possible total trip cost.
- **Spatial Pre-filtering**: Uses dynamic bounding boxes to drastically reduce the search space, filtering thousands of fuel stations down to only those physically adjacent to the route.
- **Robust Geocoding**: Includes a built-in background geocoding engine using Nominatim, featuring smart rate-limiting, error handling, and resumability.
- **Idempotent Data Loading**: Easily ingest and update thousands of fuel prices from CSV without duplicating data.

---

## 🛠️ Technology Stack

- **Backend Framework**: Django & Django REST Framework (DRF)
- **Database**: SQLite (Development)
- **External Services**: OSRM (Routing), OpenStreetMap Nominatim (Geocoding)

---

## 📖 API Documentation

### **Plan Trip**
Computes the route and optimal fuel stops.

`POST /api/v1/trip/plan/`

**Request Payload:**
```json
{
  "start": "Chicago, IL",
  "finish": "Indianapolis, IN"
}
```

**Response Payload:**
```json
{
  "route": {
    "distance_miles": 181.3,
    "duration_seconds": 11520,
    "geometry": [[-87.6244, 41.8756], [-86.1581, 39.7684]]
  },
  "fuel_stops": [
    {
      "name": "Pilot Travel Center",
      "address": "123 Highway Blvd",
      "city": "Gary",
      "state": "IN",
      "price": 3.45,
      "gallons_purchased": 18.1,
      "cost_for_stop": 62.44,
      "location": {"lat": 41.593, "lon": -87.346}
    }
  ],
  "summary": {
    "total_stops": 1,
    "total_gallons": 18.1,
    "total_fuel_cost": 62.44,
    "avg_price_per_gallon": 3.45,
    "cheapest_stop_price": 3.45,
    "most_expensive_stop_price": 3.45
  }
}
```

---

## ⚙️ Installation & Setup

**1. Clone the repository**
```bash
git clone https://github.com/Aayush10530/Spott-api.git
cd Spott-api/fuel_route_planner
```

**2. Setup Virtual Environment & Install Dependencies**
```bash
python -m venv venv
source venv/bin/activate  # On Windows use: venv\Scripts\activate
pip install -r requirements.txt
```

**3. Configure Environment Variables**
Create a `.env` file in the `fuel_route_planner` directory:
```env
SECRET_KEY=your-secret-key
DEBUG=True
OSRM_BASE_URL=http://router.project-osrm.org
NOMINATIM_USER_AGENT=FuelRoutePlanner/1.0
```

**4. Run Database Migrations**
```bash
python manage.py migrate
```

**5. Load & Geocode Fuel Stations**
Load the stations from the CSV file, and then geocode their city/state into latitude/longitude coordinates.
```bash
python manage.py load_stations
python manage.py geocode_stations --resume
```
*(Note: Geocoding is strictly rate-limited to 1 request/second to respect Nominatim's public API policies.)*

**6. Start the Development Server**
```bash
python manage.py runserver 8000
```

---

## 💡 Business Logic Constraints
- **Vehicle Fuel Efficiency**: 10 Miles Per Gallon (MPG)
- **Tank Capacity**: 50 Gallons
- **Maximum Range**: 500 Miles
- **Starting Fuel**: Full Tank (500 Miles of range)
