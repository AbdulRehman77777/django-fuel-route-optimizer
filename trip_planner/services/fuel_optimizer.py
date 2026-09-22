from dataclasses import dataclass
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_UP

from trip_planner.constants import MAX_RANGE_MILES, MPG, TANK_CAPACITY_GALLONS
from .errors import NoFeasibleRouteError
from .station_locator import RouteStation

EPSILON = Decimal("0.000001")
DISPLAY_GALLON = Decimal("0.01")
DISPLAY_PRICE = Decimal("0.01")


@dataclass(frozen=True)
class FuelPurchase:
    station: RouteStation
    gallons: Decimal
    cost: Decimal


def _usable_stations(stations, route_distance):
    best = {}
    for station in stations:
        if station.route_mile <= EPSILON or station.route_mile >= route_distance - EPSILON:
            continue
        key = station.station_id
        existing = best.get(key)
        if existing is None or (station.price, station.distance_from_route_miles) < (existing.price, existing.distance_from_route_miles):
            best[key] = station
    return sorted(best.values(), key=lambda item: item.route_mile)


def _suffix_feasibility(nodes, destination):
    feasible = [False] * len(nodes)
    for index in range(len(nodes) - 1, -1, -1):
        position = nodes[index].route_mile
        if destination - position + nodes[index].distance_from_route_miles <= MAX_RANGE_MILES + EPSILON:
            feasible[index] = True
        else:
            feasible[index] = any(
                feasible[j]
                and nodes[j].route_mile - position + nodes[index].distance_from_route_miles + nodes[j].distance_from_route_miles <= MAX_RANGE_MILES + EPSILON
                for j in range(index + 1, len(nodes))
            )
    return feasible


def _leg_distance(position, current_offset, target):
    """Distance from the current fuel pump to the next fuel pump."""
    return target.route_mile - position + current_offset + target.distance_from_route_miles


def _display_purchase(desired, available_capacity, filling_tank):
    """Quantize the actual purchase while preserving displayed tank invariants."""
    rounding = ROUND_FLOOR if filling_tank else ROUND_CEILING
    purchase = max(Decimal("0"), desired).quantize(DISPLAY_GALLON, rounding=rounding)
    capacity_limit = max(Decimal("0"), available_capacity).quantize(DISPLAY_GALLON, rounding=ROUND_FLOOR)
    return min(purchase, capacity_limit)


def optimize_fuel_stops(stations, route_distance_miles):
    """Return cost-aware purchases, assuming a free full tank at the origin.

    This is the classic linear gas-station strategy: seek the first cheaper reachable
    station; otherwise buy toward a full tank and move to the best reachable price.
    A backward feasibility pass prevents greedy choices from entering dead ends.
    """
    destination = Decimal(str(route_distance_miles))
    if destination <= MAX_RANGE_MILES + EPSILON:
        return []
    nodes = _usable_stations(stations, destination)
    feasible = _suffix_feasibility(nodes, destination)
    if not any(feasible[i] and nodes[i].route_mile + nodes[i].distance_from_route_miles <= MAX_RANGE_MILES + EPSILON for i in range(len(nodes))):
        raise NoFeasibleRouteError("No chain of fuel stations can cover this route within the 500-mile vehicle range.")

    position = Decimal("0")
    fuel = TANK_CAPACITY_GALLONS
    current_price = Decimal("0")
    current_index = -1
    current_offset = Decimal("0")
    purchases = []

    while destination - position + current_offset > fuel * MPG + EPSILON:
        reachable = [
            (i, node) for i, node in enumerate(nodes)
            if i > current_index and feasible[i] and EPSILON < _leg_distance(position, current_offset, node) <= MAX_RANGE_MILES + EPSILON
        ]
        if not reachable:
            raise NoFeasibleRouteError("A gap between usable fuel stations exceeds the 500-mile vehicle range.")

        if current_index == -1:
            # The initial tank is free, so consume as much of it as safely possible.
            next_index, next_node = max(reachable, key=lambda pair: (pair[1].route_mile, -pair[1].price))
        else:
            cheaper = [(i, node) for i, node in reachable if node.price < current_price - EPSILON]
            if cheaper:
                next_index, next_node = min(cheaper, key=lambda pair: (pair[1].route_mile, pair[1].distance_from_route_miles))
            else:
                next_index, next_node = min(reachable, key=lambda pair: (pair[1].price, pair[1].distance_from_route_miles, -pair[1].route_mile))

        travel = _leg_distance(position, current_offset, next_node)
        needed_to_next = travel / MPG
        if fuel + EPSILON < needed_to_next:
            raise NoFeasibleRouteError("The computed fuel plan would exhaust the tank before a station.")
        fuel -= needed_to_next
        if fuel < 0 and abs(fuel) <= EPSILON:
            fuel = Decimal("0")
        position = next_node.route_mile
        current_offset = next_node.distance_from_route_miles
        current_price = next_node.price
        current_index = next_index

        remaining = destination - position + current_offset
        if remaining <= fuel * MPG + EPSILON:
            break
        forward = [
            (i, node) for i, node in enumerate(nodes)
            if i > current_index and feasible[i] and _leg_distance(position, current_offset, node) <= MAX_RANGE_MILES + EPSILON
        ]
        cheaper_forward = [(i, node) for i, node in forward if node.price < current_price - EPSILON]
        if remaining <= MAX_RANGE_MILES + EPSILON:
            target_fuel = remaining / MPG
        elif cheaper_forward:
            target = min(cheaper_forward, key=lambda pair: (pair[1].route_mile, pair[1].distance_from_route_miles))[1]
            target_fuel = _leg_distance(position, current_offset, target) / MPG
        else:
            target_fuel = TANK_CAPACITY_GALLONS
        filling_tank = target_fuel >= TANK_CAPACITY_GALLONS
        desired = min(TANK_CAPACITY_GALLONS, target_fuel) - fuel
        gallons = _display_purchase(desired, TANK_CAPACITY_GALLONS - fuel, filling_tank)
        if gallons > EPSILON:
            billed_price = current_price.quantize(DISPLAY_PRICE, rounding=ROUND_HALF_UP)
            purchases.append(FuelPurchase(next_node, gallons, gallons * billed_price))
            fuel += gallons

    return purchases
