# Fuel Route Optimizer

A Django REST API that calculates a US driving route and recommends cost-effective fuel stops using the supplied fuel-price dataset while respecting a 500-mile vehicle range.

## Features

- US start and destination geocoding
- Driving route calculation through OpenRouteService/HeiGIT
- Local fuel-station and pricing database
- Bounding-box and projected route-corridor filtering
- Cost-aware, multi-stop fuel optimization
- Configurable 500-mile range, 10 MPG, and 50-gallon tank assumptions
- Detour-aware fuel feasibility and consumption
- Deterministic Decimal purchase and cost calculations
- Cached geocodes and routes
- JSON and GeoJSON responses
- Leaflet/OpenStreetMap demonstration page
- Importable Postman collection
- Fully mocked automated provider tests

## Architecture

```text
Client / Postman
        |
        v
Django REST API
        |
        +--> Geocoding Service
        +--> Routing Service
        +--> Fuel Station DB
        +--> Spatial Filtering
        +--> Fuel Optimizer
        |
        v
JSON + GeoJSON Response
```

An uncached request uses two geocoding calls and one directions call. Fuel-station coordinates are preprocessed into SQLite; bounding-box filtering, projected route-distance calculations, reachability analysis, and fuel optimization then happen locally. The application never requests an external route for every station. See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Technology

- Python 3.12+
- Django 6.0.8 and Django REST Framework
- SQLite
- OpenRouteService/HeiGIT Pelias and directions APIs
- Shapely and pyproj
- Leaflet and OpenStreetMap
- pytest and pytest-django

## Setup

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
cp .env.example .env
```

Add a valid key to the local `.env` file:

```dotenv
OPENROUTESERVICE_API_KEY=your_api_key_here
```

Never commit `.env`; it is ignored by Git.

Create the database:

```bash
python manage.py migrate
```

### Fuel data preparation

CSV importing and network geocoding are deliberately separate operations.

The fastest reproducible setup uses the committed coordinate seed. It contains only coordinates exported from the working local database and makes no network geocoding requests:

```bash
python manage.py import_fuel_prices data/fuel-prices-for-be-assessment.csv \
  --coordinates-csv data/station-coordinates.csv
```

This imports all valid US price records and attaches the available seed coordinates. The import is idempotent. Duplicate OPIS station IDs use the minimum valid retail price because the source does not distinguish duplicate product rows.

To import prices without the seed:

```bash
python manage.py import_fuel_prices data/fuel-prices-for-be-assessment.csv
```

To preprocess additional station coordinates, run small resumable batches:

```bash
python manage.py geocode_fuel_stations --limit 20 --ors-delay 1.0
```

The command uses Census batch geocoding first and a validated HeiGIT/Pelias fallback for Census failures. It pauses safely on rate limits and never runs inside the route API. Inspect progress without network access:

```bash
python manage.py geocode_fuel_stations --stats
```

## Running

```bash
python manage.py runserver
```

- Browser demo: `http://127.0.0.1:8000/`
- API: `POST http://127.0.0.1:8000/api/v1/route/`

Example request:

```json
{
  "start": "Dallas, TX",
  "finish": "Miami, FL"
}
```

Trimmed example response—the real `geometry.coordinates` and GeoJSON features are omitted here for readability:

```json
{
  "route": {
    "distance_miles": 1309.39,
    "duration_minutes": 1200.0,
    "geometry": {"type": "LineString", "coordinates": ["..."]}
  },
  "fuel_stops": [
    {
      "station_id": "example",
      "price_per_gallon": "3.15",
      "route_mile": 487.41,
      "gallons_purchased": 48.94,
      "stop_cost": "154.16"
    }
  ],
  "summary": {
    "number_of_fuel_stops": 2,
    "gallons_purchased_en_route": 81.98,
    "estimated_detour_miles": 10.38,
    "total_fuel_cost": "276.41"
  },
  "map": {"type": "FeatureCollection", "features": ["..."]}
}
```

Live routes and prices can vary with provider data and the imported price snapshot; these values are demonstration output, not hardcoded behavior.

## Fuel Assumptions

- Maximum vehicle range: 500 miles
- Fuel efficiency: 10 MPG
- Tank capacity: 50 gallons
- The vehicle starts with a full tank
- Initial fuel cost is excluded because no origin fuel price is supplied
- Selected-stop detours are estimated as round trips and participate in fuel feasibility and consumption
- `total_fuel_cost` covers fuel purchased during the route only

`route.distance_miles` remains the provider's base route. The summary separately exposes base-route fuel, estimated detour fuel, and total estimated driven miles.

## Optimization

The optimizer does not blindly stop every 500 miles. It builds a feasible chain of locally matched stations, considers reachable future prices, buys only enough to reach a cheaper station when appropriate, and otherwise buys toward capacity to make safe progress. A backward feasibility pass prevents a cheap but unreachable dead end. Tank capacity and detour-aware fuel balance are checked at every leg.

Purchase gallons and displayed prices are quantized before billing so each displayed `gallons_purchased × price_per_gallon` reproduces `stop_cost`; `total_fuel_cost` is the sum of displayed stop costs.

## Performance

- Deterministic caching for normalized location geocodes
- Cached routes for identical coordinate pairs
- Indexed database bounding-box filtering before geometry work
- Metre-based Shapely/pyproj corridor calculations
- Progressive 5, 10, and 20-mile corridor expansion only when needed
- No external directions request per fuel station

Django's local-memory cache keeps the assessment dependency-light. Redis would be the natural shared-cache replacement in a multi-worker deployment.

## Testing

External provider calls are mocked; tests require no API key:

```bash
pytest
python manage.py check
python manage.py makemigrations --check --dry-run
```

The verified suite covers API validation, live-format provider parsing, authentication and rate-limit handling, CSV import/idempotency, projected spatial filtering, cost arithmetic, detour-aware tank invariants, and multi-stop optimization.

## API Errors

Errors are structured JSON with stable codes and safe messages. Covered cases include invalid or identical inputs, locations outside the USA, provider authentication failures, rate limits, provider outages, malformed provider responses, missing fuel data, and an infeasible fuel plan. Provider secrets and raw error bodies are never returned.

## Project Structure

```text
config/                     Django settings and URLs
trip_planner/
  api/                      Serializers, views, error handling
  management/commands/      Import, geocoding, and safe probe commands
  migrations/               Database schema
  services/                 Geocoding, routing, spatial, and fuel logic
tests/                      Automated test suite
templates/map.html          Leaflet demonstration UI
data/                       Source prices and coordinate seed
docs/                       Architecture documentation
postman/                    Postman collection
```

## Postman

Import [postman/Fuel-Route-Optimizer.postman_collection.json](postman/Fuel-Route-Optimizer.postman_collection.json). It includes short-route, long-route, and invalid-request examples with basic response assertions.

## Production Improvements

- PostgreSQL/PostGIS for larger spatial datasets
- Redis for shared caching
- Background station-price and coordinate preprocessing
- Deployment-specific secret management, HTTPS, observability, throttling, and health checks
- Road-network detour calculations for only the final selected stations

This repository is intentionally scoped as a professional coding assessment rather than a complete production deployment.
