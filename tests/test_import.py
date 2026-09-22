from pathlib import Path

import pytest
from django.core.management import call_command

from trip_planner.models import FuelStation

pytestmark = pytest.mark.django_db


HEADER = "OPIS Truckstop ID,Truckstop Name,Address,City,State,Rack ID,Retail Price\n"


def write_csv(tmp_path, rows):
    path = tmp_path / "fuel.csv"
    path.write_text(HEADER + rows, encoding="utf-8")
    return path


def test_valid_invalid_non_us_and_duplicate_rows(tmp_path):
    path = write_csv(tmp_path, "1,First,1 Main,Dallas,TX,10,3.50\n1,Renamed,1 Main,Dallas,TX,10,3.10\n2,Bad,2 Main,Dallas,TX,10,nope\n3,Canada,3 Main,Toronto,ON,10,2.00\n")
    call_command("import_fuel_prices", str(path), skip_geocoding=True)
    assert FuelStation.objects.count() == 1
    station = FuelStation.objects.get()
    assert station.name == "Renamed"
    assert str(station.retail_price) == "3.1000"
    assert station.latitude is None


def test_coordinate_cache_and_repeated_import_are_safe(tmp_path):
    path = write_csv(tmp_path, "1,First,1 Main,Dallas,TX,10,3.50\n")
    coordinates = tmp_path / "coordinates.csv"
    coordinates.write_text("station_id,latitude,longitude\n1,32.77,-96.79\n", encoding="utf-8")
    call_command("import_fuel_prices", str(path), coordinates_csv=str(coordinates), skip_geocoding=True)
    call_command("import_fuel_prices", str(path), coordinates_csv=str(coordinates), skip_geocoding=True)
    assert FuelStation.objects.count() == 1
    assert FuelStation.objects.get().geocoding_status == "imported_coordinates"
