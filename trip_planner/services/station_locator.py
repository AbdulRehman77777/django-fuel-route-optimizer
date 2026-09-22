from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from math import cos, radians

from pyproj import Transformer
from shapely.geometry import LineString, Point
from shapely.ops import transform

METERS_PER_MILE = 1609.344
DISPLAY_MILES = Decimal("0.01")


@dataclass(frozen=True)
class RouteStation:
    station_id: str
    name: str
    address: str
    city: str
    state: str
    latitude: float
    longitude: float
    price: Decimal
    route_mile: Decimal
    distance_from_route_miles: Decimal


def _bbox(coordinates, corridor_miles):
    lons = [point[0] for point in coordinates]
    lats = [point[1] for point in coordinates]
    middle_lat = (min(lats) + max(lats)) / 2
    lat_pad = corridor_miles / 69.0
    lon_pad = corridor_miles / max(20.0, 69.0 * cos(radians(middle_lat)))
    return min(lons) - lon_pad, min(lats) - lat_pad, max(lons) + lon_pad, max(lats) + lat_pad


def locate_stations(route_geometry, route_distance_miles, corridor_miles, queryset):
    coordinates = route_geometry["coordinates"]
    min_lon, min_lat, max_lon, max_lat = _bbox(coordinates, corridor_miles)
    candidates = queryset.filter(latitude__isnull=False, longitude__isnull=False, latitude__gte=min_lat, latitude__lte=max_lat, longitude__gte=min_lon, longitude__lte=max_lon).only("source_station_id", "name", "address", "city", "state", "latitude", "longitude", "retail_price")
    center_lon = sum(point[0] for point in coordinates) / len(coordinates)
    center_lat = sum(point[1] for point in coordinates) / len(coordinates)
    transformer = Transformer.from_crs("EPSG:4326", f"+proj=aeqd +lat_0={center_lat} +lon_0={center_lon} +datum=WGS84 +units=m", always_xy=True)
    projected_route = transform(transformer.transform, LineString(coordinates))
    route_length = projected_route.length
    located = []
    for station in candidates.iterator(chunk_size=1000):
        point = transform(transformer.transform, Point(station.longitude, station.latitude))
        distance_miles = projected_route.distance(point) / METERS_PER_MILE
        if distance_miles <= corridor_miles:
            fraction = projected_route.project(point) / route_length if route_length else 0
            located.append(RouteStation(
                station_id=station.source_station_id, name=station.name, address=station.address,
                city=station.city, state=station.state, latitude=station.latitude, longitude=station.longitude,
                price=station.retail_price,
                route_mile=Decimal(str(fraction * route_distance_miles)).quantize(DISPLAY_MILES, rounding=ROUND_HALF_UP),
                distance_from_route_miles=Decimal(str(distance_miles)).quantize(DISPLAY_MILES, rounding=ROUND_HALF_UP),
            ))
    return sorted(located, key=lambda station: (station.route_mile, station.price, station.distance_from_route_miles))
