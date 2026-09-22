from decimal import Decimal

import pytest

from trip_planner.constants import TANK_CAPACITY_GALLONS
from trip_planner.services.cost_calculator import money, summarize
from trip_planner.services.errors import NoFeasibleRouteError
from trip_planner.services.fuel_optimizer import optimize_fuel_stops
from trip_planner.services.station_locator import RouteStation


def station(mile, price, station_id=None, offset="0"):
    return RouteStation(str(station_id or mile), f"Station {mile}", "1 Road", "City", "TX", 32.0, -97.0, Decimal(str(price)), Decimal(str(mile)), Decimal(offset))


def simulate(route_distance, purchases):
    fuel = TANK_CAPACITY_GALLONS
    position = Decimal("0")
    current_offset = Decimal("0")
    for purchase in purchases:
        travel = purchase.station.route_mile - position + current_offset + purchase.station.distance_from_route_miles
        fuel -= travel / Decimal("10")
        assert fuel >= Decimal("-0.000001")
        fuel += purchase.gallons
        assert fuel <= TANK_CAPACITY_GALLONS + Decimal("0.000001")
        position = purchase.station.route_mile
        current_offset = purchase.station.distance_from_route_miles
    fuel -= (Decimal(str(route_distance)) - position + current_offset) / Decimal("10")
    assert fuel >= Decimal("-0.000001")
    return fuel


def test_short_route_needs_no_stop():
    assert optimize_fuel_stops([], 499) == []


def test_route_above_range_requires_stop():
    purchases = optimize_fuel_stops([station(450, "3.20")], 800)
    assert len(purchases) == 1
    assert purchases[0].gallons == Decimal("30")
    simulate(800, purchases)


def test_multiple_stops_required():
    purchases = optimize_fuel_stops([station(450, "3.30"), station(900, "3.10")], 1400)
    assert len(purchases) == 2
    simulate(1400, purchases)


def test_buys_only_enough_to_reach_cheaper_station():
    purchases = optimize_fuel_stops([station(450, "4.00"), station(700, "3.00"), station(1100, "3.20")], 1200)
    assert purchases[0].station.route_mile == Decimal("450")
    assert purchases[0].gallons == Decimal("20")
    assert purchases[1].station.route_mile == Decimal("700")
    simulate(1200, purchases)


def test_equal_price_prefers_closer_to_route():
    candidates = [station(700, "3.00", "far", "4"), station(700, "3.00", "near", "1"), station(450, "4.00")]
    purchases = optimize_fuel_stops(candidates, 1050)
    assert any(item.station.station_id == "near" for item in purchases)


def test_no_cheaper_station_fills_toward_capacity():
    purchases = optimize_fuel_stops([station(450, "3.00"), station(850, "3.50")], 1200)
    assert purchases[0].gallons == Decimal("45")
    simulate(1200, purchases)


def test_destination_reachable_avoids_extra_fuel():
    purchases = optimize_fuel_stops([station(450, "3.00")], 600)
    assert purchases[0].gallons == Decimal("10")


def test_impossible_gap_raises_meaningful_error():
    with pytest.raises(NoFeasibleRouteError):
        optimize_fuel_stops([station(400, "3.00"), station(950, "2.90")], 1200)


def test_cost_is_decimal_and_deterministic():
    first = optimize_fuel_stops([station(450, "3.1999")], 800)
    second = optimize_fuel_stops([station(450, "3.1999")], 800)
    assert first[0].cost == second[0].cost == Decimal("96.0000")


def test_dallas_miami_style_plan_is_display_consistent_and_detour_feasible():
    route_distance = Decimal("1309.39")
    candidates = [
        station("487.41", "3.15", "first", "2.02"),
        station("932.75", "3.70", "second", "3.17"),
    ]
    purchases = optimize_fuel_stops(candidates, route_distance)
    assert [item.gallons for item in purchases] == [Decimal("48.94"), Decimal("33.04")]
    assert simulate(route_distance, purchases) == Decimal("0.003")
    displayed_costs = [money(item.cost) for item in purchases]
    assert displayed_costs == [Decimal("154.16"), Decimal("122.25")]
    for purchase, displayed_cost in zip(purchases, displayed_costs):
        displayed_price = money(purchase.station.price)
        assert money(purchase.gallons * displayed_price) == displayed_cost
    summary = summarize(route_distance, purchases)
    assert summary["estimated_detour_miles"] == 10.38
    assert summary["total_estimated_driven_miles"] == 1319.77
    assert summary["base_route_fuel_required_gallons"] == 130.94
    assert summary["estimated_detour_fuel_gallons"] == 1.04
    assert summary["trip_fuel_required_gallons"] == 131.98
    assert summary["total_fuel_cost"] == "276.41"
    assert Decimal(summary["total_fuel_cost"]) == sum(displayed_costs)


def test_near_500_mile_stop_includes_outbound_detour_in_reachability():
    feasible = station("497.50", "3.20", "feasible", "2.40")
    purchases = optimize_fuel_stops([feasible], Decimal("700"))
    assert purchases
    simulate(Decimal("700"), purchases)
    impossible = station("497.50", "3.20", "impossible", "2.60")
    with pytest.raises(NoFeasibleRouteError):
        optimize_fuel_stops([impossible], Decimal("700"))
