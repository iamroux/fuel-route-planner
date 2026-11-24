from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

import numpy as np

from .errors import NoRouteError

EPS = 1e-9


@dataclass(frozen=True)
class FuelOption:
    mile: float
    price: float
    ref: object


@dataclass(frozen=True)
class FuelStop:
    option: FuelOption
    gallons: float
    cost: float
    fuel_on_arrival_gallons: float


def plan_fuel_stops(options, total_miles, range_miles, mpg, stop_penalty=0.0, unit_miles=1.0):
    """Cheapest set of fuel stops for the trip, starting with an empty tank.

    DP over (station, fuel level). cost[g] is the cheapest way to arrive at the current
    station with g units of fuel, where a unit is unit_miles of driving. Filling up to h
    costs min(cost[g] - g*p) + h*p over g <= h, so a running min handles each station.

    stop_penalty is added per stop when choosing, but not to the returned costs.
    """
    stations = sorted(options, key=lambda o: o.mile)
    tank = int(np.floor(range_miles / unit_miles + EPS))
    levels = np.arange(tank + 1)
    gal_per_unit = unit_miles / mpg
    end_pos = int(round(total_miles / unit_miles))

    if not stations or int(round(stations[0].mile / unit_miles)) != 0:
        raise NoRouteError('No fuel station reachable near the start of the route.')

    cost = np.full(tank + 1, np.inf)
    cost[0] = 0.0
    pos = 0
    trail = []

    for st in stations:
        k = int(round(st.mile / unit_miles))
        if k > end_pos:
            break
        cost = _drive(cost, k - pos, st.mile)
        pos = k

        unit_price = st.price * gal_per_unit
        vals = cost - levels * unit_price
        best = np.minimum.accumulate(vals)
        best_from = np.maximum.accumulate(np.where(vals == best, levels, 0))
        if_stop = best + levels * unit_price + stop_penalty

        stopped = if_stop < cost - EPS
        cost = np.where(stopped, if_stop, cost)
        trail.append((pos, st, stopped, best_from))

    cost = _drive(cost, end_pos - pos, total_miles)
    level = int(np.argmin(cost))
    if not np.isfinite(cost[level]):
        raise NoRouteError("This trip can't be done with the fuel stations on the route.")

    # walk back from the finish to see where we stopped and how much we bought
    stops = []
    next_pos = end_pos
    for pos, st, stopped, best_from in reversed(trail):
        level += next_pos - pos
        if stopped[level]:
            arrived = int(best_from[level])
            gallons = (level - arrived) * gal_per_unit
            stops.append(FuelStop(st, gallons, gallons * st.price, arrived * gal_per_unit))
            level = arrived
        next_pos = pos
    stops.reverse()
    return stops


def _drive(cost, distance_units, at_mile):
    if distance_units == 0:
        return cost
    out = np.full_like(cost, np.inf)
    if distance_units < len(cost):
        out[:len(cost) - distance_units] = cost[distance_units:]
    if not np.isfinite(out).any():
        raise NoRouteError(
            f"No fuel station within range before mile {at_mile:.0f}, so the trip can't be done."
        )
    return out


def money(value) -> float:
    return float(Decimal(str(value)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))
