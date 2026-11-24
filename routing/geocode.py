import re
from dataclasses import dataclass

import requests
from django.conf import settings
from django.core.cache import cache

from .errors import InputError, UpstreamError
from .models import Place
from .places import normalize_city, parse_state

# rough box around the US incl. Alaska and Hawaii
US_BOUNDS = (18.0, 72.0, -180.0, -65.0)

_LATLNG = re.compile(r'^\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*$')


@dataclass(frozen=True)
class Location:
    label: str
    lat: float
    lng: float
    source: str

    def as_dict(self):
        return {'query': self.label, 'lat': self.lat, 'lng': self.lng, 'resolved_by': self.source}


def in_us_bounds(lat, lng):
    min_lat, max_lat, min_lng, max_lng = US_BOUNDS
    return min_lat <= lat <= max_lat and min_lng <= lng <= max_lng


def resolve(query: str) -> Location:
    query = (query or '').strip()
    if not query:
        raise InputError('Location is empty.')

    m = _LATLNG.match(query)
    if m:
        lat, lng = float(m.group(1)), float(m.group(2))
        if not in_us_bounds(lat, lng):
            raise InputError(f'"{query}" is not inside the USA. Use "lat,lng" order.')
        return Location(query, lat, lng, 'coordinates')

    place = _lookup_census(query)
    if place:
        return Location(query, place.lat, place.lng, 'census')

    return _lookup_nominatim(query)


def _lookup_census(query):
    if ',' not in query:
        return None
    city, _, state = query.rpartition(',')
    state_code = parse_state(state)
    if not state_code:
        return None
    return Place.objects.filter(state=state_code, key=normalize_city(city)).first()


def nominatim_search(query):
    cfg = settings.FUEL_PLANNER
    try:
        resp = requests.get(
            f"{cfg['NOMINATIM_URL']}/search",
            params={'q': query, 'format': 'jsonv2', 'countrycodes': 'us', 'limit': 1},
            headers={'User-Agent': cfg['HTTP_USER_AGENT']},
            timeout=cfg['HTTP_TIMEOUT_SECONDS'],
        )
        resp.raise_for_status()
        results = resp.json()
    except (requests.RequestException, ValueError) as exc:
        raise UpstreamError(f'Geocoding service failed: {exc}') from exc
    if not results:
        return None
    return float(results[0]['lat']), float(results[0]['lon'])


def _lookup_nominatim(query):
    cache_key = f'geocode:{normalize_city(query)}'
    hit = cache.get(cache_key)
    if hit is None:
        hit = nominatim_search(query) or 'miss'
        cache.set(cache_key, hit, settings.FUEL_PLANNER['ROUTE_CACHE_SECONDS'])
    if hit == 'miss':
        raise InputError(f'Could not find "{query}" in the USA. Try "City, ST" or "lat,lng".')
    lat, lng = hit
    return Location(query, lat, lng, 'nominatim')
