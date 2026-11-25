# Fuel Route Planner

Django API that takes a start and finish in the US and returns the route, the cheapest places to fuel along the way, and the total fuel cost. Assumes a 500 mile range and 10 mpg.

Routing uses the free [OSRM](https://project-osrm.org/) API, with one call per trip. Routes are cached, so repeat requests and the map page don't call it again.

## Setup

Needs Python 3.13+ and [uv](https://docs.astral.sh/uv/).

```bash
uv sync
uv run python manage.py migrate
uv run python manage.py load_data
uv run python manage.py runserver
```

Tests:

```bash
uv run python manage.py test routing
```

## API

### `GET /api/route/?start=Dallas, TX&finish=Chicago, IL`

Also works as `POST /api/route/` with `{"start": "...", "finish": "..."}`.

`start` and `finish` can be:

- `"City, ST"`, looked up locally
- `"lat,lng"`
- a full address, which falls back to Nominatim

Optional `stop_penalty` (default `5`) is a dollar amount added per stop when picking stations, so it doesn't stop just to save a few cents. It's not included in the returned cost. Pass `0` for the strictly cheapest plan.

Example response (trimmed):

```json
{
  "start": {"query": "New York, NY", "lat": 40.6627, "lng": -73.9387, "resolved_by": "census"},
  "finish": {"query": "Los Angeles, CA", "lat": 34.0194, "lng": -118.4108, "resolved_by": "census"},
  "summary": {
    "distance_miles": 2810.5,
    "duration_hours": 50.31,
    "total_gallons": 281.05,
    "total_fuel_cost": 859.38,
    "average_price_per_gallon": 3.06,
    "number_of_stops": 8
  },
  "fuel_stops": [
    {
      "stop": 1, "mile_marker": 0.0, "name": "Fuel 4", "city": "Jersey City", "state": "NJ",
      "price_per_gallon": 3.239, "gallons": 7.0, "cost": 22.67, "lat": 40.7114, "lng": -74.0648
    }
  ],
  "route": {"type": "Feature", "geometry": {"type": "LineString", "coordinates": ["..."]}},
  "map_url": "http://127.0.0.1:8000/api/route/map/?start=New+York%2C+NY&finish=Los+Angeles%2C+CA",
  "meta": {"routing_api_calls": 1, "route_from_cache": false, "elapsed_ms": 1310.4}
}
```

Errors:

- `400`: bad input, or a location outside the US
- `422`: no route, or a gap longer than 500 miles with no station
- `502`: OSRM or Nominatim is down

### `GET /api/route/map/?start=...&finish=...`

Leaflet map of the route and fuel stops. The JSON response links to it in `map_url`.

### `GET /api/docs/`

Swagger UI for trying the API in the browser. The OpenAPI spec is at `/api/openapi.json`. There's also a Postman collection in `postman_collection.json`.

## How it works

- The CSV has no coordinates. `load_data` matches each station's city to the [Census Gazetteer](https://www.census.gov/geographies/reference-files/time-series/geo/gazetteer-files.html) place file, which covers about 95% of them. The other 228 towns were looked up on Nominatim once and saved in `data/station_geocode_cache.json`. You can rebuild that file with `load_data --geocode-missing`.
- The OSRM route is resampled to one point per mile. A KD-tree finds the stations within 10 miles of the route and gives each one a mile marker.
- The tank starts empty, so the first stop is the station nearest the start. After that, a DP over (station, fuel level) picks the cheapest stops. With `stop_penalty=0` it gives the exact cheapest plan. The tests check that against a brute-force solver.

## Notes

- Stations are placed at their city center, so map pins can be a few miles from the real stop.
- The detour to reach a station isn't counted as fuel used.
- Stations are loaded into memory once per process, so restart the server after running `load_data` again.
