import hashlib
import json

import requests
from django.conf import settings
from django.core.cache import cache

from trip_planner.constants import METERS_PER_MILE
from .errors import ConfigurationError, MalformedProviderResponseError, ProviderRateLimitError, ProviderRequestError, ProviderUnavailableError, RouteNotFoundError
from .http import resilient_session


def _route_key(start, finish):
    raw = json.dumps([round(start[0], 6), round(start[1], 6), round(finish[0], 6), round(finish[1], 6)])
    return "route:" + hashlib.sha256(raw.encode()).hexdigest()


class OpenRouteServiceRouter:
    endpoint = "https://api.heigit.org/openrouteservice/v2/directions/driving-car/geojson"

    def __init__(self, session=None):
        self.session = session or resilient_session()

    def route(self, start, finish):
        key = _route_key(start, finish)
        if cached := cache.get(key):
            return cached
        if not settings.OPENROUTESERVICE_API_KEY:
            raise ConfigurationError("OpenRouteService is not configured.")
        try:
            response = self.session.post(
                self.endpoint,
                headers={"Authorization": settings.OPENROUTESERVICE_API_KEY, "Content-Type": "application/json"},
                json={"coordinates": [list(start), list(finish)]},
                timeout=settings.ORS_TIMEOUT_SECONDS,
            )
        except requests.exceptions.RetryError as exc:
            raise ProviderUnavailableError("The routing service retry budget was exhausted.") from exc
        except (requests.Timeout, requests.ConnectionError) as exc:
            raise ProviderUnavailableError("The routing service is temporarily unavailable.") from exc
        except requests.RequestException as exc:
            raise ProviderUnavailableError("The routing request failed safely.") from exc

        status = response.status_code
        if status in {401, 403}:
            raise ConfigurationError("OpenRouteService rejected the configured routing credentials.")
        if status == 429:
            raise ProviderRateLimitError("The routing provider rate limit has been reached.")
        if status == 400:
            raise ProviderRequestError("The routing provider rejected the route request.")
        if status == 404:
            raise RouteNotFoundError("No driving route was found between these locations.")
        if status >= 500:
            raise ProviderUnavailableError("The routing service is temporarily unavailable.")
        if status >= 400:
            raise ProviderRequestError("The routing provider rejected the route request.")
        try:
            payload = response.json()
        except ValueError as exc:
            raise MalformedProviderResponseError("The routing provider returned malformed JSON.") from exc
        try:
            feature = payload["features"][0]
            geometry = feature["geometry"]
            if geometry.get("type") != "LineString" or len(geometry.get("coordinates", [])) < 2:
                raise ValueError
            segments = feature["properties"]["segments"]
            if not isinstance(segments, list) or not segments:
                raise ValueError
            distance_meters = sum(float(segment["distance"]) for segment in segments)
            duration_seconds = sum(float(segment["duration"]) for segment in segments)
            if distance_meters <= 0 or duration_seconds < 0:
                raise ValueError
            result = {
                "distance_miles": distance_meters / float(METERS_PER_MILE),
                "duration_minutes": duration_seconds / 60,
                "geometry": geometry,
                "bbox": payload.get("bbox") or feature.get("bbox"),
            }
        except (KeyError, TypeError, ValueError, IndexError) as exc:
            raise MalformedProviderResponseError("The routing provider returned an invalid route.") from exc
        cache.set(key, result, settings.ROUTE_CACHE_SECONDS)
        return result
