# 4½-minute Loom demo script

## 0:00–0:20 — Introduction

“This is my Django fuel route optimization API. It calculates a driving route between two US locations and recommends cost-effective fuel stops using the supplied fuel-price dataset.”

## 0:20–1:30 — Postman

Open the **Long route — multiple stops** request and send it. Point out route miles and duration, then expand `fuel_stops`. Show station identity, price, route mile, off-route distance, gallons purchased, and stop cost. Show `summary.total_fuel_cost`, `base_route_fuel_required_gallons`, `estimated_detour_fuel_gallons`, `total_estimated_driven_miles`, and en-route gallons. Mention that detours participate in tank feasibility and that the free initial full tank is explicit and excluded from cost. Briefly send the invalid request to show the JSON validation error.

## 1:30–2:00 — Browser map

Open `http://127.0.0.1:8000/`, submit the same locations, and show the route, endpoints, and fuel markers. Click a marker to show price, gallons, and cost.

## 2:00–3:15 — Important code

Show `trip_planner/api/views.py`: the view orchestrates thin services and builds JSON/GeoJSON. Show `services/routing.py` and mention two cached geocodes plus one cached route call for a new trip. Show `services/station_locator.py`: an indexed bounding box narrows candidates, then projected local geometry measures the route corridor. Show `services/fuel_optimizer.py`: the optimizer considers reachable stations, seeks a cheaper station, buys only the needed fuel, and uses a backward feasibility pass to avoid dead ends. Emphasize that station searching and optimization are local and there is never a routing call per station.

## 3:15–4:00 — Reliability

Show cache settings and deterministic keys. Run `pytest` and briefly show optimizer, API, importer, routing, and spatial tests. Mention mocked external APIs, retry/timeouts, structured errors, display-consistent Decimal costs, corridor expansion, and the resumable two-stage station-geocoding command.

## 4:00–4:30 — Handoff

Show the README quick start, `.env.example`, Postman collection, and clean directory structure. Conclude: “The project is ready to run locally and push to GitHub; secrets, local databases, caches, and virtual environments are ignored.”
