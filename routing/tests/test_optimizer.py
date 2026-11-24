import random

from django.test import SimpleTestCase

from routing.errors import NoRouteError
from routing.optimizer import FuelOption, plan_fuel_stops

RANGE, MPG = 500, 10


def opt(mile, price, ref=None):
    return FuelOption(mile=mile, price=price, ref=ref if ref is not None else f'm{mile}')


def plan(options, total, penalty=0.0):
    return plan_fuel_stops(options, total, RANGE, MPG, stop_penalty=penalty)


class OptimizerTests(SimpleTestCase):
    def test_short_trip_buys_only_what_it_needs(self):
        stops = plan([opt(0, 3.0)], 200)
        self.assertEqual(len(stops), 1)
        self.assertAlmostEqual(stops[0].gallons, 20)
        self.assertAlmostEqual(stops[0].cost, 60)

    def test_buys_just_enough_to_reach_cheaper_station(self):
        stops = plan([opt(0, 4.0), opt(100, 3.0)], 400)
        self.assertEqual([s.option.mile for s in stops], [0, 100])
        self.assertAlmostEqual(stops[0].gallons, 10)
        self.assertAlmostEqual(stops[1].gallons, 30)
        self.assertAlmostEqual(sum(s.cost for s in stops), 10 * 4 + 30 * 3)

    def test_fills_up_at_cheap_station_before_expensive_stretch(self):
        stops = plan([opt(0, 3.0), opt(400, 5.0)], 800)
        self.assertAlmostEqual(stops[0].gallons, 50)
        self.assertAlmostEqual(stops[1].gallons, 30)
        self.assertAlmostEqual(stops[1].fuel_on_arrival_gallons, 10)

    def test_skips_stations_it_does_not_need(self):
        stops = plan([opt(0, 3.0), opt(150, 3.5), opt(300, 3.6)], 450)
        self.assertEqual(len(stops), 1)
        self.assertAlmostEqual(stops[0].gallons, 45)

    def test_picks_cheapest_station_in_range_when_filling(self):
        options = [opt(0, 3.0), opt(200, 3.9), opt(350, 3.2), opt(480, 3.8), opt(700, 3.5)]
        stops = plan(options, 900)
        self.assertEqual([s.option.mile for s in stops], [0, 350, 700])

    def test_total_gallons_equal_distance_over_mpg(self):
        options = [opt(m, p) for m, p in [(0, 3.4), (120, 3.1), (390, 3.6), (610, 2.9), (980, 3.3), (1300, 3.0)]]
        stops = plan(options, 1500)
        self.assertAlmostEqual(sum(s.gallons for s in stops), 150)

    def test_is_optimal_against_brute_force(self):
        options = [opt(0, 3.5), opt(90, 3.9), opt(210, 3.0), opt(380, 4.2), opt(520, 3.3), opt(640, 3.8)]
        total = 900
        got = sum(s.cost for s in plan(options, total))
        self.assertAlmostEqual(got, brute_force_cost(options, total), places=6)

    def test_matches_brute_force_on_random_routes(self):
        rng = random.Random(42)
        for _ in range(25):
            total = rng.choice(range(600, 1400, 10))
            miles = sorted({0} | {rng.randrange(10, total, 10) for _ in range(rng.randint(4, 12))})
            options = [opt(m, round(rng.uniform(2.8, 4.2), 3)) for m in miles]
            try:
                expected = brute_force_cost(options, total)
            except ValueError:
                continue
            got = sum(s.cost for s in plan(options, total))
            self.assertAlmostEqual(got, expected, places=6)

    def test_stop_penalty_skips_tiny_savings(self):
        # saves ~$1 total by stopping again, not worth a $5 penalty
        options = [opt(0, 3.02), opt(10, 3.00)]
        self.assertEqual(len(plan(options, 500, penalty=0)), 2)
        stops = plan(options, 500, penalty=5)
        self.assertEqual(len(stops), 1)
        self.assertAlmostEqual(stops[0].gallons, 50)

    def test_stop_penalty_still_takes_big_savings(self):
        stops = plan([opt(0, 4.00), opt(10, 3.00)], 500, penalty=5)
        self.assertEqual([s.option.mile for s in stops], [0, 10])
        self.assertAlmostEqual(stops[0].gallons, 1)

    def test_gap_longer_than_range_raises(self):
        with self.assertRaises(NoRouteError):
            plan([opt(0, 3.0), opt(600, 3.0)], 900)

    def test_no_station_at_start_raises(self):
        with self.assertRaises(NoRouteError):
            plan([opt(20, 3.0)], 300)


def brute_force_cost(options, total, step=10):
    # slow but simple, only used to check the real optimizer
    stations = sorted(options, key=lambda o: o.mile) + [opt(total, 0.0, 'end')]
    cap = RANGE // step
    INF = float('inf')
    best = [[INF] * (cap + 1) for _ in stations]
    best[0][0] = 0.0
    for i, s in enumerate(stations[:-1]):
        for f in range(cap + 1):
            if best[i][f] == INF:
                continue
            for buy in range(cap - f + 1):
                cost = best[i][f] + buy * step / MPG * s.price
                fuel = f + buy
                nxt = stations[i + 1]
                d = (nxt.mile - s.mile) / step
                if d <= fuel:
                    left = int(fuel - d)
                    best[i + 1][left] = min(best[i + 1][left], cost)
    if min(best[-1]) == INF:
        raise ValueError('unreachable')
    return min(best[-1])
