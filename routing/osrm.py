from dataclasses import dataclass

import requests
from django.conf import settings
from django.core.cache import cache

from .errors import NoRouteError, UpstreamError

METERS_PER_MILE = 1609.344


@dataclass(frozen=True)
class Route:
    distance_miles: float
    duration_seconds: float
    coordinates: list[tuple[float, float]]  # (lng, lat)
    from_cache: bool = False


def get_route(start_lat, start_lng, end_lat, end_lng) -> Route:
    coords = f'{start_lng:.5f},{start_lat:.5f};{end_lng:.5f},{end_lat:.5f}'
    cache_key = f'osrm:{coords}'
    data = cache.get(cache_key)
    from_cache = data is not None
    if not from_cache:
        data = _fetch(coords)
        cache.set(cache_key, data, settings.FUEL_PLANNER['ROUTE_CACHE_SECONDS'])

    return Route(
        distance_miles=data['distance'] / METERS_PER_MILE,
        duration_seconds=data['duration'],
        coordinates=[tuple(c) for c in data['geometry']['coordinates']],
        from_cache=from_cache,
    )


def _fetch(coords):
    cfg = settings.FUEL_PLANNER
    try:
        resp = requests.get(
            f"{cfg['OSRM_URL']}/route/v1/driving/{coords}",
            params={'overview': 'full', 'geometries': 'geojson', 'steps': 'false'},
            headers={'User-Agent': cfg['HTTP_USER_AGENT']},
            timeout=cfg['HTTP_TIMEOUT_SECONDS'],
        )
        data = resp.json()
    except (requests.RequestException, ValueError) as exc:
        raise UpstreamError(f'Routing service failed: {exc}') from exc

    if data.get('code') in ('NoRoute', 'NoSegment'):
        raise NoRouteError('No drivable route found between those locations.')
    if resp.status_code != 200 or data.get('code') != 'Ok' or not data.get('routes'):
        raise UpstreamError(f"Routing service error: {data.get('message') or data.get('code')}")

    route = data['routes'][0]
    return {'distance': route['distance'], 'duration': route['duration'], 'geometry': route['geometry']}
