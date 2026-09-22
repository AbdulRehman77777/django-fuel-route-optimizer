from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Count

from trip_planner.constants import GEOCODED_STATION_STATUSES
from trip_planner.models import FuelStation
from trip_planner.services.station_geocoding import ORSAuthenticationError, ORSMalformedResponse, ORSRequestError, ORSStationGeocoder, ProviderTemporarilyUnavailable, RateLimitReached, census_batch


class Command(BaseCommand):
    help = "Resumably geocode fuel stations with Census followed by validated ORS fallback."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=100, help="Maximum distinct stations to process this run (default: 100).")
        parser.add_argument("--ors-delay", "--delay", dest="ors_delay", type=float, default=1.0, help="Minimum seconds between every ORS HTTP request (default: 1.0).")
        parser.add_argument("--stats", action="store_true", help="Print database totals without making network requests.")

    def handle(self, *args, **options):
        if options["stats"]:
            self._print_stats()
            return
        limit = options["limit"]
        ors_delay = options["ors_delay"]
        if limit < 1:
            raise CommandError("--limit must be at least 1.")
        if ors_delay < 0:
            raise CommandError("--ors-delay cannot be negative.")

        counters = {"census": 0, "ors": 0, "unresolved": 0, "rate_limited": False}
        processed = 0
        ors_geocoder = ORSStationGeocoder(request_delay=ors_delay)

        # Resolve known Census failures first; they are never sent back to Census.
        failures = list(FuelStation.objects.filter(geocoding_status=FuelStation.GeocodingStatus.CENSUS_FAILED, latitude__isnull=True).order_by("pk")[:limit])
        stopped = self._run_ors(failures, ors_geocoder, counters)
        processed += len(failures) if not stopped else stopped
        if stopped:
            if not counters["rate_limited"]:
                self.stderr.write(self.style.WARNING("ORS processing paused safely; unprocessed stations remain retryable."))
            self._print_summary(counters)
            return

        remaining = limit - processed
        pending = list(FuelStation.objects.filter(geocoding_status=FuelStation.GeocodingStatus.PENDING, latitude__isnull=True).order_by("pk")[:remaining])
        if pending:
            try:
                matches = census_batch(pending)
            except ProviderTemporarilyUnavailable as exc:
                self.stderr.write(self.style.WARNING(str(exc)))
                self._print_summary(counters)
                return
            for station in pending:
                coordinates = matches.get(station.source_station_id)
                if coordinates:
                    FuelStation.objects.filter(pk=station.pk).update(latitude=coordinates[0], longitude=coordinates[1], geocoding_status=FuelStation.GeocodingStatus.CENSUS_MATCHED, geocoding_provider="census", geocoding_message="US Census batch match")
                    counters["census"] += 1
                else:
                    FuelStation.objects.filter(pk=station.pk).update(geocoding_status=FuelStation.GeocodingStatus.CENSUS_FAILED, geocoding_provider="census", geocoding_message="Census No_Match or Tie")
            failed_now = list(FuelStation.objects.filter(pk__in=[item.pk for item in pending], geocoding_status=FuelStation.GeocodingStatus.CENSUS_FAILED).order_by("pk"))
            stopped = self._run_ors(failed_now, ors_geocoder, counters)
            if stopped and not counters["rate_limited"]:
                self.stderr.write(self.style.WARNING("ORS processing paused safely; remaining Census failures stay retryable."))
        self._print_summary(counters)

    def _run_ors(self, stations, geocoder, counters):
        if stations and not settings.OPENROUTESERVICE_API_KEY:
            self.stderr.write(self.style.WARNING("OPENROUTESERVICE_API_KEY is not configured; Census failures remain retryable."))
            return 1
        for index, station in enumerate(stations):
            try:
                result = geocoder.geocode(station)
            except RateLimitReached as exc:
                counters["rate_limited"] = True
                message = "OpenRouteService rate limit reached. Batch paused safely; remaining stations are retryable."
                if exc.retry_after is not None:
                    message += f" Retry after approximately {exc.retry_after} seconds."
                self.stderr.write(self.style.WARNING(message))
                return index + 1
            except (ProviderTemporarilyUnavailable, ORSAuthenticationError, ORSRequestError, ORSMalformedResponse) as exc:
                self.stderr.write(self.style.WARNING(str(exc)))
                return index + 1
            if result:
                FuelStation.objects.filter(pk=station.pk).update(latitude=result.latitude, longitude=result.longitude, geocoding_status=FuelStation.GeocodingStatus.ORS_MATCHED, geocoding_provider="openrouteservice", geocoding_message=f"ORS confidence {result.confidence:.2f}: {result.label}"[:255])
                counters["ors"] += 1
            else:
                FuelStation.objects.filter(pk=station.pk).update(geocoding_status=FuelStation.GeocodingStatus.UNRESOLVED, geocoding_provider="openrouteservice", geocoding_message="No reliable ORS result")
                counters["unresolved"] += 1
        return 0

    def _print_summary(self, counters):
        total = FuelStation.objects.count()
        geocoded = FuelStation.objects.filter(geocoding_status__in=GEOCODED_STATION_STATUSES, latitude__isnull=False, longitude__isnull=False).count()
        remaining = FuelStation.objects.filter(geocoding_status__in=(FuelStation.GeocodingStatus.PENDING, FuelStation.GeocodingStatus.CENSUS_FAILED), latitude__isnull=True).count()
        self.stdout.write(f"Total stations: {total}")
        self.stdout.write(f"Already geocoded: {geocoded}")
        self.stdout.write(f"Census matched this run: {counters['census']}")
        self.stdout.write(f"ORS fallback matched this run: {counters['ors']}")
        self.stdout.write(f"Unresolved this run: {counters['unresolved']}")
        self.stdout.write(f"Rate limited this run: {'yes' if counters['rate_limited'] else 'no'}")
        self.stdout.write(f"Remaining pending: {remaining}")

    def _print_stats(self):
        counts = {row["geocoding_status"]: row["count"] for row in FuelStation.objects.values("geocoding_status").annotate(count=Count("id"))}
        self.stdout.write(f"Total stations: {FuelStation.objects.count()}")
        for status, _label in FuelStation.GeocodingStatus.choices:
            self.stdout.write(f"{status}: {counts.get(status, 0)}")
        geocoded = FuelStation.objects.filter(geocoding_status__in=GEOCODED_STATION_STATUSES, latitude__isnull=False, longitude__isnull=False).count()
        self.stdout.write(f"Geocoded coordinates: {geocoded}")
