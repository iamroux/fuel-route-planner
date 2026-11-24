from django.contrib import admin

from .models import Place, Station


@admin.register(Station)
class StationAdmin(admin.ModelAdmin):
    list_display = ('opis_id', 'name', 'city', 'state', 'price', 'geo_source')
    list_filter = ('state', 'geo_source')
    search_fields = ('name', 'city')


@admin.register(Place)
class PlaceAdmin(admin.ModelAdmin):
    list_display = ('name', 'state', 'lat', 'lng')
    search_fields = ('name',)
