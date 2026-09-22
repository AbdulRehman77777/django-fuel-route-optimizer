from decimal import Decimal
from unittest.mock import patch

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from trip_planner.models import FuelStation
from trip_planner.services.errors import LocationNotFoundError, ProviderUnavailableError
from trip_planner.services.fuel_optimizer import FuelPurchase
from trip_planner.services.station_locator import RouteStation

pytestmark = pytest.mark.django_db


def provider_data(distance=800):
    geocodes = [
        {"longitude": -96.8, "latitude": 32.8, "label": "Dallas, TX", "country": "US"},
        {"longitude": -80.2, "latitude": 25.8, "label": "Miami, FL", "country": "US"},
    ]
    route = {"distance_miles": distance, "duration_minutes": 700, "geometry": {"type": "LineString", "coordinates": [[-96.8, 32.8], [-80.2, 25.8]]}, "bbox": None}
    return geocodes, route


@pytest.fixture
def client():
    FuelStation.objects.create(source_station_id="1", name="Fuel", address="1 Road", city="Mobile", state="AL", retail_price=Decimal("3.10"), latitude=30.7, longitude=-88.0, geocoding_status="census_matched")
    return APIClient()


def test_invalid_request(client):
    response = client.post(reverse("route-plan"), {"start": "Dallas, TX"}, format="json")
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "validation_error"


def test_identical_request(client):
    response = client.post(reverse("route-plan"), {"start": " Dallas, TX ", "finish": "dallas, tx"}, format="json")
    assert response.status_code == 400


@patch("trip_planner.api.views.OpenRouteServiceGeocoder")
def test_geocoder_failure(geocoder_cls, client):
    geocoder_cls.return_value.geocode.side_effect = LocationNotFoundError("Not found")
    response = client.post(reverse("route-plan"), {"start": "Nope", "finish": "Miami"}, format="json")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "location_not_found"


@patch("trip_planner.api.views.OpenRouteServiceRouter")
@patch("trip_planner.api.views.OpenRouteServiceGeocoder")
def test_routing_failure(geocoder_cls, router_cls, client):
    geocodes, _ = provider_data()
    geocoder_cls.return_value.geocode.side_effect = geocodes
    router_cls.return_value.route.side_effect = ProviderUnavailableError("Unavailable")
    response = client.post(reverse("route-plan"), {"start": "Dallas", "finish": "Miami"}, format="json")
    assert response.status_code == 503


@patch("trip_planner.api.views.optimize_fuel_stops")
@patch("trip_planner.api.views.locate_stations")
@patch("trip_planner.api.views.OpenRouteServiceRouter")
@patch("trip_planner.api.views.OpenRouteServiceGeocoder")
def test_valid_long_route_response(geocoder_cls, router_cls, locate, optimize, client):
    geocodes, route = provider_data()
    geocoder_cls.return_value.geocode.side_effect = geocodes
    router_cls.return_value.route.return_value = route
    candidate = RouteStation("1", "Fuel", "1 Road", "Mobile", "AL", 30.7, -88.0, Decimal("3.10"), Decimal("450"), Decimal("1.2"))
    locate.return_value = [candidate]
    optimize.return_value = [FuelPurchase(candidate, Decimal("30"), Decimal("93"))]
    response = client.post(reverse("route-plan"), {"start": "Dallas", "finish": "Miami"}, format="json")
    assert response.status_code == 200
    payload = response.json()
    assert payload["route"]["geometry"]["type"] == "LineString"
    assert payload["summary"]["total_fuel_cost"] == "93.00"
    assert payload["fuel_stops"][0]["gallons_purchased"] == 30.0
    displayed_stop = payload["fuel_stops"][0]
    assert Decimal(str(displayed_stop["gallons_purchased"])) * Decimal(displayed_stop["price_per_gallon"]) == Decimal(displayed_stop["stop_cost"])
    assert Decimal(payload["summary"]["total_fuel_cost"]) == sum(Decimal(stop["stop_cost"]) for stop in payload["fuel_stops"])
    assert payload["map"]["type"] == "FeatureCollection"
    assert {feature["properties"]["kind"] for feature in payload["map"]["features"]} == {"route", "start", "finish", "fuel_stop"}


@patch("trip_planner.api.views.optimize_fuel_stops", return_value=[])
@patch("trip_planner.api.views.locate_stations", return_value=[])
@patch("trip_planner.api.views.OpenRouteServiceRouter")
@patch("trip_planner.api.views.OpenRouteServiceGeocoder")
def test_short_route_response(geocoder_cls, router_cls, locate, optimize, client):
    geocodes, route = provider_data(300)
    geocoder_cls.return_value.geocode.side_effect = geocodes
    router_cls.return_value.route.return_value = route
    response = client.post(reverse("route-plan"), {"start": "Dallas", "finish": "Austin"}, format="json")
    assert response.status_code == 200
    assert response.json()["fuel_stops"] == []
