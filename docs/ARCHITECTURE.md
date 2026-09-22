# Architecture

```text
Postman / Client
       |
       v
Django REST API
       |
       +--> Geocoding Service
       |
       +--> Routing Service
       |
       +--> Fuel Station DB
       |
       +--> Spatial Filter
       |
       +--> Fuel Optimizer
       |
       v
JSON + GeoJSON Response
```

## Request flow

The serializer validates the two locations. OpenRouteService geocodes each uncached location and makes one driving-route request. Geocodes and routes use deterministic cache keys. The provider is only responsible for endpoints, distance, duration, and route geometry.

Current HeiGIT endpoints:

- Pelias geocoding: `https://api.heigit.org/pelias/v1/search`
- Driving directions: `https://api.heigit.org/openrouteservice/v2/directions/driving-car/geojson`

Both calls are server-side and authenticate from `OPENROUTESERVICE_API_KEY`; credentials are never returned to clients.

Station coordinates are prepared before API use and stored in SQLite. Import is network-free, and the committed coordinate seed provides a reproducible baseline without committing the local database. A dedicated resumable command first uses Census batches, then applies a bounded and validated HeiGIT/Pelias fallback to Census failures. The live route request never geocodes fuel stations. It first applies an indexed latitude/longitude bounding-box query. Shapely and pyproj then project the route and candidates into a local metre-based coordinate system, measure perpendicular distance, and calculate each station's progress along the route. No per-station routing or geocoding requests occur.

The optimizer consumes plain data objects, not Django models. It starts with 50 gallons, uses a 500-mile reachability graph, rejects dead ends, buys only enough to reach a cheaper reachable station, and otherwise fills toward capacity before selecting the best reachable price. Edges include the current station's return-to-route distance and the next station's outbound distance, so the estimated detours participate in tank feasibility. Gallons and billing prices are Decimal-quantized to their displayed precision before costs are calculated.

The corridor starts at five miles and expands to 10 and 20 miles only when no feasible station chain exists. The response includes both normal route fields and a GeoJSON FeatureCollection for the browser map.
