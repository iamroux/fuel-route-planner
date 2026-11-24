from dataclasses import dataclass

import numpy as np
from scipy.spatial import cKDTree

EARTH_RADIUS_MILES = 3958.8


def to_xyz(lat, lng):
    # unit vectors on the sphere, so KD-tree distances work anywhere in the US
    lat, lng = np.radians(lat), np.radians(lng)
    return np.column_stack((np.cos(lat) * np.cos(lng), np.cos(lat) * np.sin(lng), np.sin(lat)))


def haversine_miles(lat1, lng1, lat2, lng2):
    lat1, lng1, lat2, lng2 = map(np.radians, (lat1, lng1, lat2, lng2))
    a = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lng2 - lng1) / 2) ** 2
    return 2 * EARTH_RADIUS_MILES * np.arcsin(np.sqrt(a))


@dataclass
class ResampledRoute:
    lats: np.ndarray
    lngs: np.ndarray
    miles: np.ndarray

    @property
    def total_miles(self) -> float:
        return float(self.miles[-1])


def resample(coordinates, step_miles=1.0, total_miles=None) -> ResampledRoute:
    """Evenly spaced points along the route, each with its mile marker.

    If total_miles is given (OSRM's road distance) the markers get scaled to it.
    """
    pts = np.asarray(coordinates, dtype=float)
    lngs, lats = pts[:, 0], pts[:, 1]
    seg = haversine_miles(lats[:-1], lngs[:-1], lats[1:], lngs[1:])
    cum = np.concatenate(([0.0], np.cumsum(seg)))
    length = cum[-1]
    if total_miles and length > 0:
        cum = cum * (total_miles / length)
        length = total_miles

    n = max(int(np.ceil(length / step_miles)), 1) + 1
    miles = np.linspace(0.0, length, n)
    return ResampledRoute(lats=np.interp(miles, cum, lats), lngs=np.interp(miles, cum, lngs), miles=miles)


def stations_near_route(route: ResampledRoute, st_lats, st_lngs, max_offset_miles):
    """Returns (station indices, mile markers, miles off route) for stations near the route."""
    pad = max_offset_miles / 69.0 + 0.05
    lng_pad = pad / max(np.cos(np.radians(np.abs(route.lats).max())), 0.2)
    in_box = np.flatnonzero(
        (st_lats >= route.lats.min() - pad) & (st_lats <= route.lats.max() + pad)
        & (st_lngs >= route.lngs.min() - lng_pad) & (st_lngs <= route.lngs.max() + lng_pad)
    )
    if in_box.size == 0:
        return np.array([], int), np.array([]), np.array([])

    tree = cKDTree(to_xyz(route.lats, route.lngs))
    chord, nearest = tree.query(to_xyz(st_lats[in_box], st_lngs[in_box]))
    offsets = chord * EARTH_RADIUS_MILES
    keep = offsets <= max_offset_miles
    return in_box[keep], route.miles[nearest[keep]], offsets[keep]
