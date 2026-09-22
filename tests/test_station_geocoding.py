from decimal import Decimal
from io import StringIO
from unittest.mock import Mock, call, patch

import pytest
import requests
from django.core.management import call_command
from django.test import override_settings

from trip_planner.models import FuelStation
from trip_planner.services.http import resilient_session
from trip_planner.services.station_geocoding import ORSMalformedResponse, ORSStationGeocoder, ProviderTemporarilyUnavailable, RateLimitReached, StationCoordinate, census_batch, normalize_highway_address

pytestmark = pytest.mark.django_db


def station(status="pending", station_id="1"):
    return FuelStation.objects.create(source_station_id=station_id, name="Pilot Travel Center", address="I-65, EXIT 246 & SR-119", city="Pelham", state="AL", retail_price=Decimal("3.10"), geocoding_status=status)


def response(json_data=None, text="", status=200):
    result = Mock(status_code=status, text=text, headers={})
    result.json.return_value = json_data
    if status >= 400:
        result.raise_for_status.side_effect = requests.HTTPError(str(status))
    return result


def valid_feature(**overrides):
    properties = {"country_a": "USA", "region_a": "AL", "layer": "venue", "confidence": 0.91, "label": "Pilot Travel Center, Pelham, AL, USA", "name": "Pilot Travel Center", "locality": "Pelham"}
    properties.update(overrides)
    return {"type": "Feature", "geometry": {"type": "Point", "coordinates": [-86.81, 33.29]}, "properties": properties}


def test_census_successful_match_and_no_match():
    first, second = station(station_id="1"), station(station_id="2")
    session = Mock()
    session.post.return_value = response(text='1,"input",Match,Exact,"address","-86.81,33.29"\n2,"input",No_Match,,,""\n')
    assert census_batch([first, second], session=session) == {"1": (33.29, -86.81)}


def test_highway_address_normalization():
    assert normalize_highway_address("I-80 & I-94, EXIT 15-A") == "I-80 I-94 Exit 15A"


@override_settings(OPENROUTESERVICE_API_KEY="super-secret-key")
def test_valid_ors_usa_state_result_is_accepted_without_exposing_key():
    item = station(status="census_failed")
    session = Mock()
    session.get.return_value = response({"features": [valid_feature()]})
    result = ORSStationGeocoder(session=session, request_delay=0).geocode(item)
    assert (result.latitude, result.longitude) == (33.29, -86.81)
    request = session.get.call_args.kwargs
    assert request["headers"]["Authorization"] == "super-secret-key"
    assert request["params"]["boundary.country"] == "USA"
    assert "api_key" not in request["params"]
    assert "super-secret-key" not in result.label


@override_settings(OPENROUTESERVICE_API_KEY="key")
@pytest.mark.parametrize("properties", [
    {"country_a": "CAN"},
    {"region_a": "TX"},
    {"confidence": 0.2},
    {"layer": "locality"},
])
def test_invalid_ors_results_are_rejected(properties):
    item = station(status="census_failed")
    session = Mock()
    session.get.return_value = response({"features": [valid_feature(**properties)]})
    assert ORSStationGeocoder(session=session, request_delay=0).geocode(item) is None


@override_settings(OPENROUTESERVICE_API_KEY="key")
def test_http_200_with_zero_features_is_normal_no_match():
    item = station(status="census_failed")
    session = Mock()
    session.get.return_value = response({"features": []})
    assert ORSStationGeocoder(session=session, request_delay=0).geocode(item) is None


@override_settings(OPENROUTESERVICE_API_KEY="key")
def test_missing_optional_confidence_is_rejected_not_exception():
    item = station(status="census_failed")
    feature = valid_feature()
    feature["properties"].pop("confidence")
    session = Mock()
    session.get.return_value = response({"features": [feature]})
    assert ORSStationGeocoder(session=session, request_delay=0).geocode(item) is None


@override_settings(OPENROUTESERVICE_API_KEY="key")
def test_http_429_is_rate_limit():
    session = Mock()
    session.get.return_value = response(status=429)
    with pytest.raises(RateLimitReached, match="rate limit"):
        ORSStationGeocoder(session=session, request_delay=0).search("Dallas, TX, USA")


@override_settings(OPENROUTESERVICE_API_KEY="key")
def test_http_500_is_temporary_server_failure():
    session = Mock()
    session.get.return_value = response(status=500)
    with pytest.raises(ProviderTemporarilyUnavailable, match="500"):
        ORSStationGeocoder(session=session, request_delay=0).search("Dallas, TX, USA")


@override_settings(OPENROUTESERVICE_API_KEY="key")
def test_connection_timeout_is_distinct_temporary_failure():
    session = Mock()
    session.get.side_effect = requests.Timeout("slow")
    with pytest.raises(ProviderTemporarilyUnavailable, match="timed out"):
        ORSStationGeocoder(session=session, request_delay=0).search("Dallas, TX, USA")


@override_settings(OPENROUTESERVICE_API_KEY="key")
def test_malformed_json_is_distinct_response_error():
    session = Mock()
    bad = response()
    bad.json.side_effect = ValueError("not json")
    session.get.return_value = bad
    with pytest.raises(ORSMalformedResponse, match="malformed JSON"):
        ORSStationGeocoder(session=session, request_delay=0).search("Dallas, TX, USA")


@override_settings(OPENROUTESERVICE_API_KEY="key")
def test_retry_error_is_converted_to_safe_provider_failure():
    session = Mock()
    session.get.side_effect = requests.exceptions.RetryError("too many 429 responses")
    with pytest.raises(ProviderTemporarilyUnavailable, match="retry budget"):
        ORSStationGeocoder(session=session, request_delay=0).search("Dallas, TX, USA")


@override_settings(OPENROUTESERVICE_API_KEY="key")
def test_throttling_occurs_between_each_query_variant():
    item = station(status="census_failed")
    session = Mock()
    session.get.return_value = response({"features": []})
    sleeper = Mock()
    assert ORSStationGeocoder(session=session, request_delay=1.0, sleeper=sleeper).geocode(item) is None
    assert session.get.call_count == 3
    assert sleeper.call_args_list == [call(1.0), call(1.0)]


def test_retry_configuration_excludes_429_and_bounds_server_retries():
    retry = resilient_session().get_adapter("https://").max_retries
    assert 429 not in retry.status_forcelist
    assert set(retry.status_forcelist) == {500, 502, 503, 504}
    assert retry.status == 2
    assert retry.raise_on_status is False


@override_settings(OPENROUTESERVICE_API_KEY="key")
@patch("trip_planner.management.commands.geocode_fuel_stations.ORSStationGeocoder")
@patch("trip_planner.management.commands.geocode_fuel_stations.census_batch")
def test_census_no_match_falls_back_to_ors(census, geocoder_cls):
    item = station()
    census.return_value = {}
    geocoder_cls.return_value.geocode.return_value = StationCoordinate(33.29, -86.81, "query", 0.9, "Pilot Pelham AL")
    call_command("geocode_fuel_stations", limit=1, ors_delay=0)
    item.refresh_from_db()
    assert item.geocoding_status == "ors_matched"
    assert item.geocoding_provider == "openrouteservice"


@override_settings(OPENROUTESERVICE_API_KEY="key")
@patch("trip_planner.management.commands.geocode_fuel_stations.ORSStationGeocoder")
@patch("trip_planner.management.commands.geocode_fuel_stations.census_batch")
def test_unreliable_fallback_becomes_unresolved(census, geocoder_cls):
    item = station()
    census.return_value = {}
    geocoder_cls.return_value.geocode.return_value = None
    call_command("geocode_fuel_stations", limit=1, ors_delay=0)
    item.refresh_from_db()
    assert item.geocoding_status == "unresolved"
    assert item.latitude is None


@override_settings(OPENROUTESERVICE_API_KEY="key")
@patch("trip_planner.management.commands.geocode_fuel_stations.ORSStationGeocoder")
@patch("trip_planner.management.commands.geocode_fuel_stations.census_batch")
def test_already_geocoded_station_is_not_retried(census, geocoder_cls):
    item = station(status="census_matched")
    item.latitude, item.longitude = 33.29, -86.81
    item.save()
    call_command("geocode_fuel_stations", limit=1, ors_delay=0)
    census.assert_not_called()
    geocoder_cls.return_value.geocode.assert_not_called()


@override_settings(OPENROUTESERVICE_API_KEY="key")
@patch("trip_planner.management.commands.geocode_fuel_stations.ORSStationGeocoder")
def test_provider_failure_leaves_station_retryable(geocoder_cls):
    item = station(status="census_failed")
    geocoder_cls.return_value.geocode.side_effect = ProviderTemporarilyUnavailable("temporary")
    call_command("geocode_fuel_stations", limit=1, ors_delay=0, stderr=StringIO())
    item.refresh_from_db()
    assert item.geocoding_status == "census_failed"


@patch("trip_planner.management.commands.geocode_fuel_stations.census_batch")
def test_stats_makes_no_network_requests(census):
    station()
    output = StringIO()
    call_command("geocode_fuel_stations", stats=True, stdout=output)
    census.assert_not_called()
    assert "pending: 1" in output.getvalue()


@override_settings(OPENROUTESERVICE_API_KEY="key")
@patch("trip_planner.management.commands.geocode_fuel_stations.ORSStationGeocoder")
def test_first_429_pauses_cleanly_and_keeps_station_retryable(geocoder_cls):
    item = station(status="census_failed")
    geocoder_cls.return_value.geocode.side_effect = RateLimitReached(retry_after=30)
    output, errors = StringIO(), StringIO()
    call_command("geocode_fuel_stations", limit=1, ors_delay=0, stdout=output, stderr=errors)
    item.refresh_from_db()
    assert item.geocoding_status == "census_failed"
    assert "Rate limited this run: yes" in output.getvalue()
    assert "Batch paused safely" in errors.getvalue()
    assert "30 seconds" in errors.getvalue()


@override_settings(OPENROUTESERVICE_API_KEY="key")
@patch("trip_planner.management.commands.geocode_fuel_stations.ORSStationGeocoder")
def test_success_before_429_is_committed_and_later_station_is_retryable(geocoder_cls):
    first = station(status="census_failed", station_id="1")
    second = station(status="census_failed", station_id="2")
    geocoder_cls.return_value.geocode.side_effect = [
        StationCoordinate(33.29, -86.81, "query", 0.9, "Pilot Pelham AL"),
        RateLimitReached(),
    ]
    output = StringIO()
    call_command("geocode_fuel_stations", limit=2, ors_delay=0, stdout=output, stderr=StringIO())
    first.refresh_from_db()
    second.refresh_from_db()
    assert first.geocoding_status == "ors_matched"
    assert first.latitude == 33.29
    assert second.geocoding_status == "census_failed"
    assert "ORS fallback matched this run: 1" in output.getvalue()
    assert "Rate limited this run: yes" in output.getvalue()
