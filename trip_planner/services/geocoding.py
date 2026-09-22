import hashlib

import requests
from django.conf import settings
from django.core.cache import cache

from .errors import ConfigurationError, LocationNotFoundError, LocationOutsideUSError, MalformedProviderResponseError, ProviderUnavailableError
from .http import resilient_session


def _cache_key(query):
    normalized = " ".join(query.lower().split())
    return "geocode:" + hashlib.sha256(normalized.encode()).hexdigest()


class OpenRouteServiceGeocoder:
    endpoint = "https://api.heigit.org/pelias/v1/search"

    def __init__(self, session=None):
        self.session = session or resilient_session()

    def geocode(self, query):
        key = _cache_key(query)
        if cached := cache.get(key):
            return cached
        if not settings.OPENROUTESERVICE_API_KEY:
            raise ConfigurationError("OpenRouteService is not configured.")
        try:
            response = self.session.get(self.endpoint, headers={"Authorization": settings.OPENROUTESERVICE_API_KEY}, params={"text": query, "boundary.country": "USA", "size": 1}, timeout=settings.ORS_TIMEOUT_SECONDS)
            if response.status_code in {401, 403}:
                raise ConfigurationError("OpenRouteService rejected the configured credentials.")
            if response.status_code == 429 or response.status_code >= 500:
                raise ProviderUnavailableError("The geocoding service is temporarily unavailable.")
            response.raise_for_status()
            payload = response.json()
        except (ConfigurationError, ProviderUnavailableError):
            raise
        except (requests.RequestException, ValueError) as exc:
            raise ProviderUnavailableError("The geocoding service is temporarily unavailable.") from exc
        features = payload.get("features") if isinstance(payload, dict) else None
        if not features:
            raise LocationNotFoundError(f"Location not found: {query}")
        try:
            feature = features[0]
            lon, lat = feature["geometry"]["coordinates"][:2]
            properties = feature.get("properties", {})
            country = str(properties.get("country_a") or properties.get("country_code") or "").upper()
            result = {"latitude": float(lat), "longitude": float(lon), "label": properties.get("label", query), "country": country}
        except (KeyError, TypeError, ValueError, IndexError) as exc:
            raise MalformedProviderResponseError("The geocoding provider returned an invalid response.") from exc
        if country not in {"US", "USA"}:
            raise LocationOutsideUSError(f"Location must be within the United States: {query}")
        cache.set(key, result, settings.GEOCODE_CACHE_SECONDS)
        return result
