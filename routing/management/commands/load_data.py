import csv
import json
import time
from decimal import Decimal

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction

from routing.errors import UpstreamError
from routing.geocode import in_us_bounds, nominatim_search
from routing.models import Place, Station
from routing.places import US_STATES, census_keys, normalize_city

GAZETTEER_FILE = '2024_Gaz_place_national.txt'
STATIONS_FILE = 'fuel-prices-for-be-assessment.csv'
GEOCODE_CACHE_FILE = 'station_geocode_cache.json'


class Command(BaseCommand):
    help = 'Load Census places and fuel stations (with coordinates) into the database.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--geocode-missing',
            action='store_true',
            help='Look up towns missing from the Census data on Nominatim (1 request/second).',
        )

    def handle(self, *args, geocode_missing=False, **options):
        data_dir = settings.DATA_DIR
        places = self.load_places(data_dir / GAZETTEER_FILE)
        cache_path = data_dir / GEOCODE_CACHE_FILE
        geo_cache = json.loads(cache_path.read_text()) if cache_path.exists() else {}

        rows = self.read_stations(data_dir / STATIONS_FILE)

        if geocode_missing:
            self.fill_geocode_cache(rows, places, geo_cache, cache_path)

        stations, unmatched = [], []
        for r in rows:
            key = (r['state'], normalize_city(r['city']))
            if key in places:
                (lat, lng), source = places[key], Station.GeoSource.CENSUS
            elif geo_cache.get(cache_key(*key)):
                (lat, lng), source = geo_cache[cache_key(*key)], Station.GeoSource.NOMINATIM
            else:
                unmatched.append(r)
                continue
            stations.append(Station(lat=lat, lng=lng, geo_source=source, **r))

        with transaction.atomic():
            Station.objects.all().delete()
            Station.objects.bulk_create(stations, batch_size=1000)

        self.stdout.write(self.style.SUCCESS(
            f'Loaded {len(stations)} stations ({len(unmatched)} skipped, no coordinates).'
        ))
        if unmatched and not geocode_missing:
            self.stdout.write('Run with --geocode-missing to look up the skipped towns.')

    def load_places(self, path):
        primary, aliases, objs = {}, {}, []
        with open(path, encoding='utf-8') as f:
            reader = csv.reader(f, delimiter='\t')
            next(reader)
            for row in reader:
                state, name = row[0], row[3]
                lat, lng = float(row[10]), float(row[11].strip())
                main_key, alias_keys = census_keys(name)
                primary.setdefault((state, main_key), (lat, lng))
                objs.append(Place(state=state, key=main_key, name=name, lat=lat, lng=lng))
                for a in alias_keys:
                    aliases.setdefault((state, a), (lat, lng, name))

        for (state, key), (lat, lng, name) in aliases.items():
            if (state, key) not in primary:
                primary[(state, key)] = (lat, lng)
                objs.append(Place(state=state, key=key, name=name, lat=lat, lng=lng))

        with transaction.atomic():
            Place.objects.all().delete()
            Place.objects.bulk_create(objs, batch_size=5000)
        self.stdout.write(f'Loaded {len(objs)} place keys from the Census Gazetteer.')
        return primary

    def read_stations(self, path):
        by_id = {}
        with open(path, encoding='utf-8') as f:
            for row in csv.DictReader(f):
                state = row['State'].strip()
                if state not in US_STATES:  # skip canadian stations
                    continue
                opis_id = int(row['OPIS Truckstop ID'])
                price = Decimal(row['Retail Price']).quantize(Decimal('0.001'))
                current = by_id.get(opis_id)
                if current and current['price'] <= price:
                    continue
                by_id[opis_id] = {
                    'opis_id': opis_id,
                    'name': row['Truckstop Name'].strip(),
                    'address': ' '.join(row['Address'].split()),
                    'city': row['City'].strip(),
                    'state': state,
                    'price': price,
                }
        return list(by_id.values())

    def fill_geocode_cache(self, rows, places, geo_cache, cache_path):
        todo = sorted({
            (r['state'], r['city']) for r in rows
            if (r['state'], normalize_city(r['city'])) not in places
            and cache_key(r['state'], normalize_city(r['city'])) not in geo_cache
        })
        self.stdout.write(f'Geocoding {len(todo)} towns on Nominatim (about {len(todo)}s)...')
        for i, (state, city) in enumerate(todo, 1):
            try:
                hit = nominatim_search(f'{city}, {US_STATES[state]}, USA')
            except UpstreamError as exc:
                self.stderr.write(f'  {city}, {state}: {exc}')
                continue
            if hit and not in_us_bounds(*hit):
                hit = None
            geo_cache[cache_key(state, normalize_city(city))] = list(hit) if hit else None
            if i % 25 == 0:
                self.stdout.write(f'  {i}/{len(todo)}')
                cache_path.write_text(json.dumps(geo_cache, indent=0, sort_keys=True))
            time.sleep(1.1)  # nominatim allows 1 req/sec
        cache_path.write_text(json.dumps(geo_cache, indent=0, sort_keys=True))


def cache_key(state, normalized_city):
    return f'{state}|{normalized_city}'
