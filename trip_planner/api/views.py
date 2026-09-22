from decimal import Decimal
from time import perf_counter

from django.conf import settings
from rest_framework.response import Response
from rest_framework.views import APIView

from trip_planner.constants import GEOCODED_STATION_STATUSES, MAX_RANGE_MILES, MPG, TANK_CAPACITY_GALLONS
from trip_planner.models import FuelStation
from trip_planner.services.cost_calculator import gallons, money, summarize
from trip_planner.services.errors import FuelDataMissingError, NoFeasibleRouteError
from trip_planner.services.fuel_optimizer import optimize_fuel_stops
from trip_planner.services.geocoding import OpenRouteServiceGeocoder
from trip_planner.services.routing import OpenRouteServiceRouter
from trip_planner.services.station_locator import locate_stations
from .serializers import RouteRequestSerializer


def _point_feature(coordinates, kind, properties=None):
    return {"type": "Feature", "geometry": {"type": "Point", "coordinates": coordinates}, "properties": {"kind": kind, **(properties or {})}}


class RoutePlanView(APIView):
    def post(self, request):
        started = perf_counter()
        serializer = RouteRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        start_text, finish_text = serializer.validated_data["start"], serializer.validated_data["finish"]

        geocoder = OpenRouteServiceGeocoder()
        start = geocoder.geocode(start_text)
        finish = geocoder.geocode(finish_text)
        start_coordinates = (start["longitude"], start["latitude"])
        finish_coordinates = (finish["longitude"], finish["latitude"])
        route = OpenRouteServiceRouter().route(start_coordinates, finish_coordinates)
        route_distance_miles = float(gallons(Decimal(str(route["distance_miles"]))))

        stations = FuelStation.objects.filter(geocoding_status__in=GEOCODED_STATION_STATUSES, latitude__isnull=False, longitude__isnull=False)
        if not stations.exists():
            raise FuelDataMissingError("No geocoded fuel stations are available. Run the fuel-price import command first.")

        purchases = None
        used_corridor = None
        for corridor in settings.ROUTE_CORRIDORS_MILES:
            nearby = locate_stations(route["geometry"], route_distance_miles, corridor, stations)
            try:
                purchases = optimize_fuel_stops(nearby, route_distance_miles)
                used_corridor = corridor
                break
            except NoFeasibleRouteError:
                continue
        if purchases is None:
            raise NoFeasibleRouteError("No feasible station chain was found, even after expanding the route corridor.")

        stop_payload = []
        stop_features = []
        for purchase in purchases:
            station = purchase.station
            item = {
                "station_id": station.station_id, "name": station.name, "address": station.address,
                "city": station.city, "state": station.state, "latitude": station.latitude,
                "longitude": station.longitude, "price_per_gallon": str(money(station.price)),
                "route_mile": float(gallons(station.route_mile)),
                "distance_from_route_miles": float(gallons(station.distance_from_route_miles)),
                "gallons_purchased": float(gallons(purchase.gallons)), "stop_cost": str(money(purchase.cost)),
            }
            stop_payload.append(item)
            stop_features.append(_point_feature([station.longitude, station.latitude], "fuel_stop", item))

        route_feature = {"type": "Feature", "geometry": route["geometry"], "properties": {"kind": "route", "distance_miles": route_distance_miles}}
        summary = summarize(route_distance_miles, purchases)
        response = {
            "request": {"start": start_text, "finish": finish_text},
            "route": {"distance_miles": route_distance_miles, "duration_minutes": round(route["duration_minutes"], 1), "geometry": route["geometry"]},
            "vehicle": {"max_range_miles": int(MAX_RANGE_MILES), "mpg": int(MPG), "tank_capacity_gallons": int(TANK_CAPACITY_GALLONS), "starting_tank_assumption": "full"},
            "fuel_stops": stop_payload,
            "summary": summary,
            "map": {"type": "FeatureCollection", "features": [route_feature, _point_feature(list(start_coordinates), "start", {"label": start["label"]}), _point_feature(list(finish_coordinates), "finish", {"label": finish["label"]}), *stop_features]},
            "assumptions": ["Vehicle starts with a full 50-gallon tank.", "The cost of the initial tank is not included.", "Fuel-station detours are locally estimated as twice the perpendicular route distance."],
            "metadata": {"station_corridor_miles": used_corridor, "processing_ms": round((perf_counter() - started) * 1000, 1)},
        }
        return Response(response)
