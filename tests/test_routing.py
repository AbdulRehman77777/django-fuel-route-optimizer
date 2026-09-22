from unittest.mock import Mock

import pytest
import requests
from django.core.cache import cache
from django.test import override_settings

from trip_planner.services.errors import ConfigurationError, MalformedProviderResponseError, ProviderRateLimitError, ProviderRequestError, ProviderUnavailableError, RouteNotFoundError
from trip_planner.services.routing import OpenRouteServiceRouter

START = (-96.784359, 32.736212)
FINISH = (-97.7431, 30.2672)


@pytest.fixture(autouse=True)
def clear_route_cache():
    cache.clear()


def feature_collection(segments=None, geometry=None):
    return {
        "type": "FeatureCollection",
        "bbox": [-97.8, 30.2, -96.7, 32.8],
        "features": [{
            "type": "Feature",
            "properties": {"segments": segments if segments is not None else [{"distance": 312701.4, "duration": 11232.2}]},
            "geometry": geometry if geometry is not None else {"type": "LineString", "coordinates": [[-96.784359, 32.736212], [-97.0, 31.5], [-97.7431, 30.2672]]},
        }],
    }


def http_response(status=200, payload=None):
    response = Mock(status_code=status)
    response.json.return_value = feature_collection() if payload is None else payload
    return response


@override_settings(OPENROUTESERVICE_API_KEY="secret", ROUTE_CACHE_SECONDS=60)
def test_valid_live_format_feature_collection_and_request_contract():
    session = Mock()
    session.post.return_value = http_response()
    route = OpenRouteServiceRouter(session=session).route(START, FINISH)
    request = session.post.call_args
    assert request.args[0] == "https://api.heigit.org/openrouteservice/v2/directions/driving-car/geojson"
    assert request.kwargs["json"] == {"coordinates": [[-96.784359, 32.736212], [-97.7431, 30.2672]]}
    assert request.kwargs["headers"]["Authorization"] == "secret"
    assert request.kwargs["headers"]["Content-Type"] == "application/json"
    assert route["distance_miles"] == pytest.approx(312701.4 / 1609.344)
    assert route["duration_minutes"] == pytest.approx(11232.2 / 60)
    assert route["geometry"]["type"] == "LineString"
    assert len(route["geometry"]["coordinates"]) == 3
    assert route["bbox"] == [-97.8, 30.2, -96.7, 32.8]


@override_settings(OPENROUTESERVICE_API_KEY="secret")
def test_multiple_segments_are_summed():
    session = Mock()
    session.post.return_value = http_response(payload=feature_collection(segments=[{"distance": 1000, "duration": 60}, {"distance": 2000, "duration": 120}]))
    route = OpenRouteServiceRouter(session=session).route(START, FINISH)
    assert route["distance_miles"] == pytest.approx(3000 / 1609.344)
    assert route["duration_minutes"] == 3


@override_settings(OPENROUTESERVICE_API_KEY="secret")
def test_empty_features_is_malformed_not_route_not_found():
    session = Mock()
    session.post.return_value = http_response(payload={"type": "FeatureCollection", "features": []})
    with pytest.raises(MalformedProviderResponseError):
        OpenRouteServiceRouter(session=session).route(START, FINISH)


@override_settings(OPENROUTESERVICE_API_KEY="secret")
@pytest.mark.parametrize("status", [401, 403])
def test_authentication_errors_are_configuration_errors(status):
    session = Mock()
    session.post.return_value = http_response(status=status)
    with pytest.raises(ConfigurationError, match="credentials"):
        OpenRouteServiceRouter(session=session).route(START, FINISH)


@override_settings(OPENROUTESERVICE_API_KEY="secret")
def test_400_is_rejected_provider_request():
    session = Mock()
    session.post.return_value = http_response(status=400)
    with pytest.raises(ProviderRequestError):
        OpenRouteServiceRouter(session=session).route(START, FINISH)


@override_settings(OPENROUTESERVICE_API_KEY="secret")
def test_404_is_actual_route_not_found():
    session = Mock()
    session.post.return_value = http_response(status=404)
    with pytest.raises(RouteNotFoundError):
        OpenRouteServiceRouter(session=session).route(START, FINISH)


@override_settings(OPENROUTESERVICE_API_KEY="secret")
def test_429_is_rate_limit_error():
    session = Mock()
    session.post.return_value = http_response(status=429)
    with pytest.raises(ProviderRateLimitError):
        OpenRouteServiceRouter(session=session).route(START, FINISH)


@override_settings(OPENROUTESERVICE_API_KEY="secret")
def test_500_is_provider_unavailable():
    session = Mock()
    session.post.return_value = http_response(status=500)
    with pytest.raises(ProviderUnavailableError):
        OpenRouteServiceRouter(session=session).route(START, FINISH)


@override_settings(OPENROUTESERVICE_API_KEY="secret")
def test_timeout_is_provider_unavailable():
    session = Mock()
    session.post.side_effect = requests.Timeout("slow")
    with pytest.raises(ProviderUnavailableError):
        OpenRouteServiceRouter(session=session).route(START, FINISH)


@override_settings(OPENROUTESERVICE_API_KEY="secret")
def test_malformed_json_is_provider_response_error():
    session = Mock()
    response = http_response()
    response.json.side_effect = ValueError("invalid json")
    session.post.return_value = response
    with pytest.raises(MalformedProviderResponseError, match="malformed JSON"):
        OpenRouteServiceRouter(session=session).route(START, FINISH)


@override_settings(OPENROUTESERVICE_API_KEY="secret")
@pytest.mark.parametrize("payload", [
    feature_collection(geometry={"type": "LineString", "coordinates": []}),
    feature_collection(segments=[]),
    {"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {}, "geometry": {"type": "LineString", "coordinates": [[0, 0], [1, 1]]}}]},
])
def test_missing_geometry_or_segment_data_is_malformed(payload):
    session = Mock()
    session.post.return_value = http_response(payload=payload)
    with pytest.raises(MalformedProviderResponseError):
        OpenRouteServiceRouter(session=session).route(START, FINISH)
