from django.core.management.base import BaseCommand, CommandError

from trip_planner.services.errors import TripPlannerError
from trip_planner.services.routing import OpenRouteServiceRouter


class Command(BaseCommand):
    help = "Make one sanitized ORS route probe through the Django routing service."

    def add_arguments(self, parser):
        parser.add_argument("--start-lon", type=float, required=True)
        parser.add_argument("--start-lat", type=float, required=True)
        parser.add_argument("--finish-lon", type=float, required=True)
        parser.add_argument("--finish-lat", type=float, required=True)

    def handle(self, *args, **options):
        start = (options["start_lon"], options["start_lat"])
        finish = (options["finish_lon"], options["finish_lat"])
        try:
            route = OpenRouteServiceRouter().route(start, finish)
        except TripPlannerError as exc:
            raise CommandError(f"{exc.code}: {exc.message}") from exc
        geometry = route["geometry"]
        self.stdout.write("Provider success: yes")
        self.stdout.write(f"Distance miles: {route['distance_miles']:.2f}")
        self.stdout.write(f"Duration minutes: {route['duration_minutes']:.2f}")
        self.stdout.write(f"Geometry type: {geometry.get('type', '')}")
        self.stdout.write(f"Route coordinates: {len(geometry.get('coordinates', []))}")
