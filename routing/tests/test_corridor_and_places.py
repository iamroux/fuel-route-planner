import numpy as np
from django.test import SimpleTestCase

from routing import corridor
from routing.places import census_keys, normalize_city, parse_state


class CorridorTests(SimpleTestCase):
    def setUp(self):
        # straight road along 35N, about 113 miles
        self.coords = [(-100.0, 35.0), (-99.0, 35.0), (-98.0, 35.0)]

    def test_resample_spacing_and_total(self):
        r = corridor.resample(self.coords, step_miles=1.0)
        self.assertAlmostEqual(r.total_miles, 113.4, delta=0.5)
        self.assertTrue(np.allclose(np.diff(r.miles), r.miles[1], atol=1e-9))
        self.assertLessEqual(r.miles[1], 1.0)

    def test_resample_scales_to_road_distance(self):
        r = corridor.resample(self.coords, total_miles=130.0)
        self.assertAlmostEqual(r.total_miles, 130.0)

    def test_stations_near_route(self):
        r = corridor.resample(self.coords)
        lats = np.array([35.0, 35.05, 35.5, 40.0])
        lngs = np.array([-99.0, -98.5, -99.0, -99.0])
        idx, miles, offsets = corridor.stations_near_route(r, lats, lngs, max_offset_miles=10)
        self.assertEqual(idx.tolist(), [0, 1])
        self.assertAlmostEqual(miles[0], 56.7, delta=1.5)
        self.assertLess(offsets[0], 0.5)
        self.assertAlmostEqual(offsets[1], 3.45, delta=0.3)


class PlaceMatchingTests(SimpleTestCase):
    def test_normalize(self):
        self.assertEqual(normalize_city('  St. Louis '), normalize_city('Saint Louis'))
        self.assertEqual(normalize_city('Mc Calla'), normalize_city('McCalla'))
        self.assertEqual(normalize_city('Ft Worth'), normalize_city('Fort Worth'))

    def test_census_keys(self):
        self.assertEqual(census_keys('Oklahoma City city')[0], 'oklahomacity')
        self.assertEqual(census_keys('Abanda CDP')[0], 'abanda')
        self.assertIn('augusta', census_keys('Augusta-Richmond County consolidated government (balance)')[1])
        self.assertIn('boise', census_keys('Boise City city')[1])
        self.assertEqual(census_keys('Town of Pecos city')[0], 'pecos')

    def test_parse_state(self):
        self.assertEqual(parse_state(' tx'), 'TX')
        self.assertEqual(parse_state('New Mexico'), 'NM')
        self.assertIsNone(parse_state('ON'))
