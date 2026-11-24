from django.db import models


class Place(models.Model):
    state = models.CharField(max_length=2)
    key = models.CharField(max_length=128)
    name = models.CharField(max_length=128)
    lat = models.FloatField()
    lng = models.FloatField()

    class Meta:
        indexes = [models.Index(fields=['state', 'key'])]

    def __str__(self):
        return f'{self.name}, {self.state}'


class Station(models.Model):
    class GeoSource(models.TextChoices):
        CENSUS = 'census', 'Census place match'
        NOMINATIM = 'nominatim', 'Nominatim'

    opis_id = models.IntegerField(unique=True)
    name = models.CharField(max_length=128)
    address = models.CharField(max_length=255)
    city = models.CharField(max_length=128)
    state = models.CharField(max_length=2)
    price = models.DecimalField(max_digits=6, decimal_places=3)
    lat = models.FloatField()
    lng = models.FloatField()
    geo_source = models.CharField(max_length=16, choices=GeoSource.choices)

    def __str__(self):
        return f'{self.name} ({self.city}, {self.state})'
