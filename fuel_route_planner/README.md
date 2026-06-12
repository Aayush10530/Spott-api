# Fuel Route Planner

## Overview
A Django REST API to calculate the optimal driving route between a starting and finishing location in the USA. It computes fuel stops along the way at the most cost-effective stations within a 50-mile threshold, using a specific fuel efficiency algorithm.

## Tech Stack
- Django 5.2
- Django REST Framework (DRF)
- SQLite
- OSRM (free routing API)
- Nominatim (free geocoding API)

## Setup

1. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Environment Variables:**
   ```bash
   cp .env.example .env
   # Update variables in .env if needed
   ```

3. **Database Setup & Data Loading:**
   ```bash
   python manage.py makemigrations trip
   python manage.py migrate
   python manage.py load_stations
   python manage.py geocode_stations
   ```

## Running the API

Start the development server:
```bash
python manage.py runserver
```

### POST `/api/v1/trip/plan/`
**Payload:**
```json
{
  "start": "New York, NY",
  "finish": "Los Angeles, CA"
}
```
**Response:**
Returns a JSON payload with the optimized route coordinates, distance, duration, and an ordered list of fuel stops.
