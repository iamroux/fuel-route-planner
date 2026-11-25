from django.urls import path

from . import views

urlpatterns = [
    path('route/', views.route_plan, name='route-plan'),
    path('route/map/', views.route_map, name='route-map'),
    path('openapi.json', views.api_schema, name='api-schema'),
    path('docs/', views.api_docs, name='api-docs'),
]
