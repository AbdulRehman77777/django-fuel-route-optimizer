import csv
import logging
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from trip_planner.constants import US_STATE_CODES
from trip_planner.models import FuelStation

LOGGER = logging.getLogger(__name__)
REQUIRED_COLUMNS = {"OPIS Truckstop ID", "Truckstop Name", "Address", "City", "State", "Retail Price"}


def clean(value):
    return " ".join((value or "").strip().split())


def load_coordinate_cache(path):
    if not path:
        return {}
    with Path(path).open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        result = {}
        for row in reader:
            station_id = clean(row.get("station_id") or row.get("OPIS Truckstop ID"))
            try:
                result[station_id] = (float(row["latitude"]), float(row["longitude"]))
            except (KeyError, TypeError, ValueError):
                continue
        return result


class Command(BaseCommand):
    help = "Import fuel prices idempotently without making geocoding network requests."

    def add_arguments(self, parser):
        parser.add_argument("csv_path")
        parser.add_argument("--coordinates-csv", help="Previously geocoded CSV with station_id, latitude, longitude.")
        parser.add_argument("--skip-geocoding", action="store_true", help="Deprecated compatibility flag; import is always network-free.")

    def handle(self, *args, **options):
        source = Path(options["csv_path"])
        if not source.exists():
            raise CommandError(f"CSV not found: {source}")
        coordinate_cache = load_coordinate_cache(options.get("coordinates_csv"))
        records = self._read(source)
        created = updated = 0
        for station_id, row in records.items():
            coordinates = coordinate_cache.get(station_id)
            existing = FuelStation.objects.filter(source_station_id=station_id).first()
            defaults = {**row}
            if coordinates:
                defaults.update(latitude=coordinates[0], longitude=coordinates[1], geocoding_status=FuelStation.GeocodingStatus.IMPORTED_COORDINATES, geocoding_provider="coordinate_cache", geocoding_message="Imported coordinate cache")
            elif existing is None:
                defaults["geocoding_status"] = "pending"
            _, was_created = FuelStation.objects.update_or_create(source_station_id=station_id, defaults=defaults)
            created += was_created
            updated += not was_created
        self.stdout.write(self.style.SUCCESS(f"Imported {len(records)} unique stations ({created} created, {updated} updated)."))

    def _read(self, source):
        records = {}
        with source.open(newline="", encoding="utf-8-sig") as handle:
            reader = csv.DictReader(handle)
            missing = REQUIRED_COLUMNS - set(reader.fieldnames or [])
            if missing:
                raise CommandError("Missing required columns: " + ", ".join(sorted(missing)))
            for line_number, raw in enumerate(reader, 2):
                station_id = clean(raw.get("OPIS Truckstop ID"))
                state = clean(raw.get("State")).upper()
                try:
                    price = Decimal(clean(raw.get("Retail Price")))
                    if price <= 0:
                        raise InvalidOperation
                except (InvalidOperation, ValueError):
                    LOGGER.warning("Skipping line %s: invalid price", line_number)
                    continue
                if not station_id or state not in US_STATE_CODES:
                    LOGGER.warning("Skipping line %s: invalid station ID or non-US state", line_number)
                    continue
                row = {"name": clean(raw.get("Truckstop Name")), "address": clean(raw.get("Address")), "city": clean(raw.get("City")), "state": state, "rack_id": clean(raw.get("Rack ID")), "retail_price": price}
                existing = records.get(station_id)
                if existing is None or price < existing["retail_price"]:
                    records[station_id] = row
        return records
