from unittest import mock

import requests

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from routing import planner
from routing.models import Place, Station

LOCMEM = {'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache', 'LOCATION': 'tests'}}

# straight road along 35N, about 680 miles
ROUTE_COORDS = [[-100.0 + i * 0.5, 35.0] for i in range(25)]


def osrm_response(*args, **kwargs):
    resp = mock.Mock(status_code=200)
    resp.json.return_value = {
        'code': 'Ok',
        'routes': [{'distance': 680 * 1609.344, 'duration': 10 * 3600,
                    'geometry': {'type': 'LineString', 'coordinates': ROUTE_COORDS}}],
    }
    return resp


@override_settings(CACHES=LOCMEM)
class RouteApiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        Place.objects.create(state='OK', key='westville', name='Westville city', lat=35.0, lng=-100.0)
        Place.objects.create(state='AR', key='eastville', name='Eastville city', lat=35.0, lng=-88.0)
        stations = [
            (1, 'START STOP', 35.01, -99.99, '3.900'),
            (2, 'CHEAP EARLY', 35.02, -99.50, '3.000'),
            (3, 'MID PRICEY', 35.00, -94.00, '4.100'),
            (4, 'MID CHEAP', 35.03, -93.00, '3.200'),
            (5, 'OFF ROUTE CHEAPEST', 36.5, -95.0, '1.000'),
        ]
        for opis, name, lat, lng, price in stations:
            Station.objects.create(opis_id=opis, name=name, address='I-40', city='X', state='OK',
                                   price=price, lat=lat, lng=lng, geo_source='census')

    def setUp(self):
        cache.clear()
        planner.reset_station_index()
        patcher = mock.patch('routing.osrm.requests.get', side_effect=osrm_response)
        self.osrm = patcher.start()
        self.addCleanup(patcher.stop)

    def test_plans_cheapest_stops(self):
        resp = self.client.get(reverse('route-plan'), {'start': 'Westville, OK', 'finish': 'Eastville, AR'})
        self.assertEqual(resp.status_code, 200, resp.content)
        data = resp.json()

        names = [s['name'] for s in data['fuel_stops']]
        self.assertEqual(names, ['START STOP', 'CHEAP EARLY', 'MID CHEAP'])
        self.assertNotIn('OFF ROUTE CHEAPEST', names)

        s = data['summary']
        self.assertAlmostEqual(s['total_gallons'], 68.0, places=1)
        self.assertAlmostEqual(s['total_fuel_cost'], sum(x['cost'] for x in data['fuel_stops']), delta=0.02)
        self.assertEqual(data['start']['resolved_by'], 'census')
        self.assertEqual(data['route']['geometry']['type'], 'LineString')
        self.assertIn('/api/route/map/?start=Westville', data['map_url'])
        self.assertEqual(data['meta']['routing_api_calls'], 1)

    def test_second_request_and_map_reuse_cached_route(self):
        params = {'start': 'Westville, OK', 'finish': 'Eastville, AR'}
        self.client.get(reverse('route-plan'), params)
        again = self.client.get(reverse('route-plan'), params).json()
        map_page = self.client.get(reverse('route-map'), params)

        self.assertEqual(self.osrm.call_count, 1)
        self.assertEqual(again['meta']['routing_api_calls'], 0)
        self.assertEqual(map_page.status_code, 200)
        self.assertContains(map_page, 'MID CHEAP')
        self.assertContains(map_page, 'leaflet')

    def test_post_json_with_coordinates(self):
        resp = self.client.post(reverse('route-plan'), {'start': '35.0,-100.0', 'finish': '35.0,-88.0'},
                                content_type='application/json')
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.json()['start']['resolved_by'], 'coordinates')

    def test_missing_input(self):
        resp = self.client.get(reverse('route-plan'), {'start': 'Westville, OK'})
        self.assertEqual(resp.status_code, 400)
        self.assertIn('error', resp.json())

    def test_location_outside_usa(self):
        resp = self.client.get(reverse('route-plan'), {'start': '51.5,-0.12', 'finish': 'Eastville, AR'})
        self.assertEqual(resp.status_code, 400)

    def test_unreachable_gap_returns_422(self):
        Station.objects.filter(opis_id__in=[3, 4]).delete()
        resp = self.client.get(reverse('route-plan'), {'start': 'Westville, OK', 'finish': 'Eastville, AR'})
        self.assertEqual(resp.status_code, 422)

    def test_upstream_failure_returns_502(self):
        self.osrm.side_effect = requests.ConnectionError('down')
        resp = self.client.get(reverse('route-plan'), {'start': 'Westville, OK', 'finish': 'Eastville, AR'})
        self.assertEqual(resp.status_code, 502)


class ApiDocsTests(TestCase):
    def test_schema_lists_route_endpoints(self):
        spec = self.client.get(reverse('api-schema')).json()
        self.assertEqual(spec['openapi'], '3.0.3')
        self.assertIn('/api/route/', spec['paths'])
        self.assertEqual(set(spec['paths']['/api/route/']), {'get', 'post'})

    def test_docs_page_loads_swagger(self):
        resp = self.client.get(reverse('api-docs'))
        self.assertContains(resp, 'swagger-ui-bundle.js')
        self.assertContains(resp, reverse('api-schema'))
