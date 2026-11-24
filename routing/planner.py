import threading
import time
from dataclasses import dataclass

import numpy as np
from django.conf import settings
from scipy.spatial import cKDTree

from . import corridor, geocode, osrm
from .errors import NoRouteError
from .models import Station
from .optimizer import FuelOption, money, plan_fuel_stops


@dataclass
class StationIndex:
    stations: list
    lats: np.ndarray
    lngs: np.ndarray
    prices: np.ndarray
    tree: cKDTree

    @classmethod
    def build(cls):
        stations = list(Station.objects.all().order_by('id'))
        lats = np.array([s.lat for s in stations], dtype=float)
        lngs = np.array([s.lng for s in stations], dtype=float)
        prices = np.array([float(s.price) for s in stations], dtype=float)
        tree = cKDTree(corridor.to_xyz(lats, lngs)) if stations else None
        return cls(stations, lats, lngs, prices, tree)

    def nearest(self, lat, lng):
        chord, idx = self.tree.query(corridor.to_xyz(np.array([lat]), np.array([lng]))[0])
        return int(idx), float(chord * corridor.EARTH_RADIUS_MILES)


_index = None
_index_lock = threading.Lock()


def get_station_index() -> StationIndex:
    global _index
    if _index is None:
        with _index_lock:
            if _index is None:
                _index = StationIndex.build()
    return _index


def reset_station_index():
    global _index
    _index = None


def plan_trip(start_query: str, finish_query: str, stop_penalty: float | None = None) -> dict:
    t0 = time.perf_counter()
    cfg = settings.FUEL_PLANNER
    range_miles, mpg = cfg['VEHICLE_RANGE_MILES'], cfg['MILES_PER_GALLON']
    if stop_penalty is None:
        stop_penalty = cfg['STOP_PENALTY_USD']

    start = geocode.resolve(start_query)
    finish = geocode.resolve(finish_query)

    index = get_station_index()
    if not index.stations:
        raise NoRouteError('No fuel stations loaded. Run "python manage.py load_data" first.')

    # truck starts empty so it has to fuel near the start. checking before routing to save the call
    first_idx, first_dist = index.nearest(start.lat, start.lng)
    if first_dist > cfg['START_SEARCH_MILES']:
        raise NoRouteError(
            f"No fuel station within {cfg['START_SEARCH_MILES']} miles of the start, "
            'and the truck starts with an empty tank.')

    route = osrm.get_route(start.lat, start.lng, finish.lat, finish.lng)
    path = corridor.resample(route.coordinates, step_miles=1.0, total_miles=route.distance_miles)
    total_miles = path.total_miles

    idxs, miles, offsets = corridor.stations_near_route(
        path, index.lats, index.lngs, cfg['CORRIDOR_MILES'])
    offset_by_idx = dict(zip(idxs.tolist(), offsets.tolist()))
    options = [FuelOption(mile=float(m), price=float(index.prices[i]), ref=int(i))
               for i, m in zip(idxs, miles)]
    options = [o for o in options if o.ref != first_idx]
    options.append(FuelOption(mile=0.0, price=float(index.prices[first_idx]), ref=first_idx))
    offset_by_idx[first_idx] = first_dist

    unit = float(path.miles[1]) if len(path.miles) > 1 else 1.0
    stops = plan_fuel_stops(options, total_miles, range_miles, mpg,
                            stop_penalty=stop_penalty, unit_miles=unit)

    total_cost = sum(s.cost for s in stops)
    total_gallons = sum(s.gallons for s in stops)
    return {
        'start': start.as_dict(),
        'finish': finish.as_dict(),
        'vehicle': {'range_miles': range_miles, 'mpg': mpg, 'tank_gallons': range_miles / mpg,
                    'starts_with_empty_tank': True},
        'summary': {
            'distance_miles': round(total_miles, 1),
            'duration_hours': round(route.duration_seconds / 3600, 2),
            'total_gallons': round(total_gallons, 2),
            'total_fuel_cost': money(total_cost),
            'average_price_per_gallon': money(total_cost / total_gallons) if total_gallons else None,
            'number_of_stops': len(stops),
            'stations_considered': len(options),
            'stop_penalty_usd': stop_penalty,
        },
        'fuel_stops': [_stop_dict(n, s, index, offset_by_idx) for n, s in enumerate(stops, 1)],
        'route': {
            'type': 'Feature',
            'properties': {'source': 'OSRM', 'resampled_every_miles': 1},
            'geometry': {
                'type': 'LineString',
                'coordinates': [[round(float(x), 5), round(float(y), 5)]
                                for x, y in zip(path.lngs, path.lats)],
            },
        },
        'meta': {
            'routing_api_calls': 0 if route.from_cache else 1,
            'route_from_cache': route.from_cache,
            'elapsed_ms': round((time.perf_counter() - t0) * 1000, 1),
        },
    }


def _stop_dict(n, stop, index, offset_by_idx):
    i = stop.option.ref
    st = index.stations[i]
    return {
        'stop': n,
        'mile_marker': round(stop.option.mile, 1),
        'opis_id': st.opis_id,
        'name': st.name,
        'address': st.address,
        'city': st.city,
        'state': st.state,
        'price_per_gallon': float(st.price),
        'gallons': round(stop.gallons, 2),
        'cost': money(stop.cost),
        'fuel_on_arrival_gallons': round(stop.fuel_on_arrival_gallons, 2),
        'miles_off_route': round(offset_by_idx.get(i, 0.0), 1),
        'lat': st.lat,
        'lng': st.lng,
    }
