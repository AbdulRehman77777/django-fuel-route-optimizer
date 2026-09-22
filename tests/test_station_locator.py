from decimal import Decimal

import pytest

from trip_planner.models import FuelStation
from trip_planner.services.station_locator import locate_stations

pytestmark = pytest.mark.django_db


def make_station(station_id, lat, lon):
    return FuelStation.objects.create(source_station_id=station_id, name=station_id, address="Road", city="City", state="TX", retail_price=Decimal("3.00"), latitude=lat, longitude=lon, geocoding_status="census_matched")


def test_near_station_included_far_station_excluded():
    make_station("near", 32.01, -97.5)
    make_station("far", 33.0, -97.5)
    geometry = {"type": "LineString", "coordinates": [[-98.0, 32.0], [-97.0, 32.0]]}
    result = locate_stations(geometry, 60, 5, FuelStation.objects.all())
    assert [item.station_id for item in result] == ["near"]


def test_stations_are_ordered_by_route_progress():
    make_station("late", 32.0, -97.2)
    make_station("early", 32.0, -97.8)
    geometry = {"type": "LineString", "coordinates": [[-98.0, 32.0], [-97.0, 32.0]]}
    result = locate_stations(geometry, 60, 5, FuelStation.objects.all())
    assert [item.station_id for item in result] == ["early", "late"]
    assert result[0].route_mile < result[1].route_mile
