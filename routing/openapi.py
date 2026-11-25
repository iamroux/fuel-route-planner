LOCATION_HELP = '"City, ST", "lat,lng", or a full US address.'

ERROR_RESPONSE = {'$ref': '#/components/schemas/Error'}


def _error(description, example):
    return {
        'description': description,
        'content': {'application/json': {'schema': ERROR_RESPONSE, 'example': {'error': example}}},
    }


ERRORS = {
    '400': _error('Bad input, or a location outside the US',
                  '"51.5074,-0.1278" is not inside the USA. Use "lat,lng" order.'),
    '422': _error('No route, or a gap longer than the vehicle range with no station',
                  "No fuel station within range before mile 960, so the trip can't be done."),
    '502': _error('OSRM or Nominatim is down', 'Routing service failed: connection timed out'),
}

PLAN_RESPONSE = {
    'description': 'Route, fuel stops and total cost',
    'content': {'application/json': {'schema': {'$ref': '#/components/schemas/Plan'}}},
}

SPEC = {
    'openapi': '3.0.3',
    'info': {
        'title': 'Fuel Route Planner',
        'version': '1.0',
        'description': 'Route between two US locations with the cheapest fuel stops. '
                       '500 mile range, 10 mpg, tank starts empty.',
    },
    'servers': [{'url': '/'}],
    'paths': {
        '/api/route/': {
            'get': {
                'summary': 'Plan a trip',
                'operationId': 'planRouteGet',
                'parameters': [
                    {'name': 'start', 'in': 'query', 'required': True, 'description': LOCATION_HELP,
                     'schema': {'type': 'string'}, 'example': 'New York, NY'},
                    {'name': 'finish', 'in': 'query', 'required': True, 'description': LOCATION_HELP,
                     'schema': {'type': 'string'}, 'example': 'Los Angeles, CA'},
                    {'name': 'stop_penalty', 'in': 'query', 'required': False,
                     'description': 'Dollars added per stop when picking stations (not part of the cost). '
                                    'Default 5, use 0 for the strictly cheapest plan.',
                     'schema': {'type': 'number', 'minimum': 0, 'maximum': 100}},
                ],
                'responses': {'200': PLAN_RESPONSE, **ERRORS},
            },
            'post': {
                'summary': 'Plan a trip (JSON body)',
                'operationId': 'planRoutePost',
                'requestBody': {
                    'required': True,
                    'content': {'application/json': {
                        'schema': {'$ref': '#/components/schemas/PlanRequest'},
                        'examples': {
                            'cities': {'summary': 'Dallas to Chicago',
                                       'value': {'start': 'Dallas, TX', 'finish': 'Chicago, IL'}},
                            'coordinates': {'summary': 'Seattle to Miami (lat,lng)',
                                            'value': {'start': '47.6062,-122.3321',
                                                      'finish': '25.7617,-80.1918'}},
                            'outside_us': {'summary': 'Error: start outside the US',
                                           'value': {'start': '51.5074,-0.1278', 'finish': 'Chicago, IL'}},
                        },
                    }},
                },
                'responses': {'200': PLAN_RESPONSE, **ERRORS},
            },
        },
        '/api/route/map/': {
            'get': {
                'summary': 'Map of the trip',
                'description': 'HTML page with the route and fuel stops. Same params as GET /api/route/. '
                               'Open the `map_url` from a plan response in a browser.',
                'operationId': 'routeMap',
                'parameters': [
                    {'name': 'start', 'in': 'query', 'required': True, 'schema': {'type': 'string'},
                     'example': 'New York, NY'},
                    {'name': 'finish', 'in': 'query', 'required': True, 'schema': {'type': 'string'},
                     'example': 'Los Angeles, CA'},
                ],
                'responses': {'200': {'description': 'HTML map', 'content': {'text/html': {}}}},
            },
        },
    },
    'components': {
        'schemas': {
            'PlanRequest': {
                'type': 'object',
                'required': ['start', 'finish'],
                'properties': {
                    'start': {'type': 'string', 'description': LOCATION_HELP},
                    'finish': {'type': 'string', 'description': LOCATION_HELP},
                    'stop_penalty': {'type': 'number', 'minimum': 0, 'maximum': 100},
                },
            },
            'Location': {
                'type': 'object',
                'properties': {
                    'query': {'type': 'string'},
                    'lat': {'type': 'number'},
                    'lng': {'type': 'number'},
                    'resolved_by': {'type': 'string', 'enum': ['coordinates', 'census', 'nominatim']},
                },
            },
            'FuelStop': {
                'type': 'object',
                'properties': {
                    'stop': {'type': 'integer'},
                    'mile_marker': {'type': 'number'},
                    'opis_id': {'type': 'integer'},
                    'name': {'type': 'string'},
                    'address': {'type': 'string'},
                    'city': {'type': 'string'},
                    'state': {'type': 'string'},
                    'price_per_gallon': {'type': 'number'},
                    'gallons': {'type': 'number'},
                    'cost': {'type': 'number'},
                    'fuel_on_arrival_gallons': {'type': 'number'},
                    'miles_off_route': {'type': 'number'},
                    'lat': {'type': 'number'},
                    'lng': {'type': 'number'},
                },
            },
            'Plan': {
                'type': 'object',
                'properties': {
                    'start': {'$ref': '#/components/schemas/Location'},
                    'finish': {'$ref': '#/components/schemas/Location'},
                    'vehicle': {
                        'type': 'object',
                        'properties': {
                            'range_miles': {'type': 'number'},
                            'mpg': {'type': 'number'},
                            'tank_gallons': {'type': 'number'},
                            'starts_with_empty_tank': {'type': 'boolean'},
                        },
                    },
                    'summary': {
                        'type': 'object',
                        'properties': {
                            'distance_miles': {'type': 'number'},
                            'duration_hours': {'type': 'number'},
                            'total_gallons': {'type': 'number'},
                            'total_fuel_cost': {'type': 'number'},
                            'average_price_per_gallon': {'type': 'number'},
                            'number_of_stops': {'type': 'integer'},
                            'stations_considered': {'type': 'integer'},
                            'stop_penalty_usd': {'type': 'number'},
                        },
                    },
                    'fuel_stops': {'type': 'array', 'items': {'$ref': '#/components/schemas/FuelStop'}},
                    'route': {'type': 'object', 'description': 'GeoJSON Feature with a LineString'},
                    'map_url': {'type': 'string'},
                    'meta': {
                        'type': 'object',
                        'properties': {
                            'routing_api_calls': {'type': 'integer'},
                            'route_from_cache': {'type': 'boolean'},
                            'elapsed_ms': {'type': 'number'},
                        },
                    },
                },
            },
            'Error': {'type': 'object', 'properties': {'error': {'type': 'string'}}},
        },
    },
}
