from decimal import Decimal, ROUND_HALF_UP

from trip_planner.constants import MPG


MONEY = Decimal("0.01")
GALLONS = Decimal("0.01")


def money(value):
    return Decimal(value).quantize(MONEY, rounding=ROUND_HALF_UP)


def gallons(value):
    return Decimal(value).quantize(GALLONS, rounding=ROUND_HALF_UP)


def summarize(route_distance_miles, purchases):
    distance = Decimal(str(route_distance_miles))
    detour_distance = sum((item.station.distance_from_route_miles * 2 for item in purchases), Decimal("0"))
    total_distance = distance + detour_distance
    displayed_costs = [money(item.cost) for item in purchases]
    return {
        "number_of_fuel_stops": len(purchases),
        "base_route_fuel_required_gallons": float(gallons(distance / MPG)),
        "estimated_detour_fuel_gallons": float(gallons(detour_distance / MPG)),
        "trip_fuel_required_gallons": float(gallons(total_distance / MPG)),
        "gallons_purchased_en_route": float(gallons(sum((item.gallons for item in purchases), Decimal("0")))),
        "estimated_detour_miles": float(gallons(detour_distance)),
        "total_estimated_driven_miles": float(gallons(total_distance)),
        "total_fuel_cost": str(money(sum(displayed_costs, Decimal("0")))),
    }
