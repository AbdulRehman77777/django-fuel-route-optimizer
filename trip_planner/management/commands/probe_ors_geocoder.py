from django.core.management.base import BaseCommand, CommandError

from trip_planner.services.station_geocoding import ORSAuthenticationError, ORSMalformedResponse, ORSRequestError, ORSStationGeocoder, ProviderTemporarilyUnavailable, RateLimitReached


class Command(BaseCommand):
    help = "Make one sanitized ORS Pelias development probe; never prints credentials."

    def add_arguments(self, parser):
        parser.add_argument("query", nargs="?", default="Dallas, TX, USA")

    def handle(self, *args, **options):
        try:
            result = ORSStationGeocoder().search(options["query"])
        except (RateLimitReached, ProviderTemporarilyUnavailable, ORSAuthenticationError, ORSRequestError, ORSMalformedResponse) as exc:
            raise CommandError(str(exc)) from exc
        label = ""
        coordinates = ""
        if result.features:
            first = result.features[0] if isinstance(result.features[0], dict) else {}
            properties = first.get("properties") if isinstance(first.get("properties"), dict) else {}
            geometry = first.get("geometry") if isinstance(first.get("geometry"), dict) else {}
            label = str(properties.get("label") or properties.get("name") or "")
            raw_coordinates = geometry.get("coordinates")
            if isinstance(raw_coordinates, list) and len(raw_coordinates) >= 2:
                coordinates = f"{raw_coordinates[0]}, {raw_coordinates[1]}"
        self.stdout.write(f"HTTP status: {result.http_status}")
        self.stdout.write(f"Result count: {len(result.features)}")
        self.stdout.write(f"First result label: {label}")
        self.stdout.write(f"First result coordinates: {coordinates}")
