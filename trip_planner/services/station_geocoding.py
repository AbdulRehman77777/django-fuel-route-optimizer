import csv
import io
import logging
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from difflib import SequenceMatcher
from email.utils import parsedate_to_datetime

import requests
from django.conf import settings

from trip_planner.models import FuelStation
from .http import resilient_session

CENSUS_ENDPOINT = "https://geocoding.geo.census.gov/geocoder/geographies/addressbatch"
ORS_GEOCODE_ENDPOINT = "https://api.heigit.org/pelias/v1/search"
ACCEPTED_LAYERS = {"address", "venue", "street", "intersection"}
HIGHWAY_RE = re.compile(r"\b(?:INTERSTATE|I)[-\s]?(\d{1,3})\b", re.IGNORECASE)
EXIT_RE = re.compile(r"\bEXIT\s*([0-9]+)\s*[- ]?([A-Z])?\b", re.IGNORECASE)
STATE_RE = re.compile(r"^[A-Z]{2}$")


class ProviderTemporarilyUnavailable(Exception):
    pass


class RateLimitReached(ProviderTemporarilyUnavailable):
    def __init__(self, retry_after=None, remaining=None, reset=None):
        super().__init__("OpenRouteService rate limit reached.")
        self.retry_after = retry_after
        self.remaining = remaining
        self.reset = reset


class ORSAuthenticationError(Exception):
    pass


class ORSRequestError(Exception):
    pass


class ORSMalformedResponse(Exception):
    pass


LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class StationCoordinate:
    latitude: float
    longitude: float
    query: str
    confidence: float
    label: str


@dataclass(frozen=True)
class PeliasSearchResult:
    http_status: int
    features: list


def normalize_highway_address(address):
    """Convert common truck-stop highway notation to Pelias-friendly text."""
    value = " ".join(address.replace("&", " ").replace(",", " ").split())
    value = HIGHWAY_RE.sub(lambda match: f"I-{match.group(1)}", value)
    value = EXIT_RE.sub(lambda match: f"Exit {match.group(1)}{match.group(2) or ''}", value)
    return value


def station_queries(station):
    exact = f"{station.address}, {station.city}, {station.state}, USA"
    normalized_address = normalize_highway_address(station.address)
    normalized = f"{normalized_address}, {station.city}, {station.state}, USA"
    named = f"{station.name}, {station.city}, {station.state}, USA"
    queries = []
    for query in (exact, normalized, named):
        if query.casefold() not in {item.casefold() for item in queries}:
            queries.append(query)
    return queries


def census_batch(stations, session=None):
    session = session or requests.Session()
    payload = io.StringIO()
    writer = csv.writer(payload)
    for station in stations:
        writer.writerow([station.source_station_id, station.address, station.city, station.state, ""])
    try:
        response = session.post(
            CENSUS_ENDPOINT,
            files={"addressFile": ("stations.csv", payload.getvalue())},
            data={"benchmark": "Public_AR_Current", "vintage": "Current_Current", "returntype": "locations"},
            timeout=120,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        raise ProviderTemporarilyUnavailable("Census batch geocoder is temporarily unavailable.") from exc

    matches = {}
    for row in csv.reader(io.StringIO(response.text)):
        try:
            station_id, status, coordinates = row[0], row[2], row[5]
            if status.casefold() != "match" or not coordinates:
                continue
            longitude, latitude = map(float, coordinates.split(","))
            if -180 <= longitude <= 180 and -90 <= latitude <= 90:
                matches[station_id] = (latitude, longitude)
        except (IndexError, TypeError, ValueError):
            continue
    return matches


def _normalized_tokens(value):
    return {token for token in re.findall(r"[a-z0-9]+", value.casefold()) if len(token) > 1 and token not in {"usa", "the", "exit"}}


def _state_matches(properties, expected_state):
    values = {str(properties.get(key, "")).strip().upper() for key in ("region_a", "region")}
    return expected_state.upper() in values


def _validate_feature(feature, station):
    try:
        properties = feature["properties"]
        longitude, latitude = feature["geometry"]["coordinates"][:2]
    except (KeyError, TypeError, ValueError, IndexError):
        return False, "missing or invalid geometry/properties"
    try:
        confidence = float(properties.get("confidence", 0))
        longitude, latitude = float(longitude), float(latitude)
    except (TypeError, ValueError):
        return False, "invalid coordinates or confidence"
    country = str(properties.get("country_a") or properties.get("country_code") or "").upper()
    layer = str(properties.get("layer", "")).casefold()
    if country not in {"US", "USA"}:
        return False, "country is not USA"
    if not _state_matches(properties, station.state):
        return False, "state does not match"
    if layer not in ACCEPTED_LAYERS:
        return False, f"unsupported layer: {layer or 'missing'}"
    if confidence < 0.60:
        return False, "confidence below 0.60 or missing"
    if not (-125 <= longitude <= -66 and 24 <= latitude <= 50):
        return False, "coordinates outside continental USA bounds"

    label = " ".join(str(properties.get(key, "")) for key in ("label", "name", "street"))
    identity = _normalized_tokens(station.address) | _normalized_tokens(station.name)
    label_tokens = _normalized_tokens(label)
    locality = str(properties.get("locality") or properties.get("localadmin") or "")
    city_similarity = SequenceMatcher(None, locality.casefold(), station.city.casefold()).ratio() if locality else 0
    has_identity_match = bool(identity & label_tokens)
    if not has_identity_match:
        return False, "station/address identity does not match"
    if locality and city_similarity < 0.55 and len(identity & label_tokens) < 2:
        return False, "locality does not match"
    return True, "accepted"


class ORSStationGeocoder:
    def __init__(self, session=None, request_delay=1.0, sleeper=time.sleep):
        self.session = session or resilient_session()
        self.request_delay = request_delay
        self.sleeper = sleeper
        self._request_started = False

    def _throttle(self):
        if self._request_started and self.request_delay:
            self.sleeper(self.request_delay)
        self._request_started = True

    def search(self, query):
        if not settings.OPENROUTESERVICE_API_KEY:
            raise ORSAuthenticationError("OPENROUTESERVICE_API_KEY is not configured.")
        self._throttle()
        try:
            response = self.session.get(
                ORS_GEOCODE_ENDPOINT,
                headers={"Authorization": settings.OPENROUTESERVICE_API_KEY},
                params={"text": query, "boundary.country": "USA", "size": 5},
                timeout=settings.ORS_TIMEOUT_SECONDS,
            )
        except requests.exceptions.RetryError as exc:
            raise ProviderTemporarilyUnavailable("OpenRouteService retry budget was exhausted.") from exc
        except (requests.Timeout, requests.ConnectionError) as exc:
            raise ProviderTemporarilyUnavailable("OpenRouteService connection failed or timed out.") from exc
        except requests.RequestException as exc:
            raise ProviderTemporarilyUnavailable("OpenRouteService request failed safely.") from exc
        status = response.status_code
        if status == 429:
            raise RateLimitReached(
                retry_after=_parse_retry_after(response.headers.get("Retry-After")),
                remaining=response.headers.get("X-RateLimit-Remaining"),
                reset=response.headers.get("X-RateLimit-Reset"),
            )
        if status in {401, 403}:
            raise ORSAuthenticationError(f"OpenRouteService rejected authentication (HTTP {status}).")
        if status >= 500:
            raise ProviderTemporarilyUnavailable(f"OpenRouteService server error (HTTP {status}).")
        if status >= 400:
            raise ORSRequestError(f"OpenRouteService rejected the geocoding request (HTTP {status}).")
        try:
            payload = response.json()
        except ValueError as exc:
            raise ORSMalformedResponse(f"OpenRouteService returned malformed JSON (HTTP {status}).") from exc
        if not isinstance(payload, dict) or not isinstance(payload.get("features"), list):
            raise ORSMalformedResponse(f"OpenRouteService response has no valid features array (HTTP {status}).")
        LOGGER.debug("ORS HTTP status: %s; features returned: %s", status, len(payload["features"]))
        return PeliasSearchResult(status, payload["features"])

    def geocode(self, station):
        for query in station_queries(station):
            search_result = self.search(query)
            for feature in search_result.features:
                accepted, reason = _validate_feature(feature, station)
                if accepted:
                    properties = feature["properties"]
                    longitude, latitude = feature["geometry"]["coordinates"][:2]
                    return StationCoordinate(float(latitude), float(longitude), query, float(properties.get("confidence", 0)), str(properties.get("label", "")))
                LOGGER.debug("Candidate rejected: %s", reason)
        return None


def _parse_retry_after(value):
    if not value:
        return None
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        try:
            parsed = parsedate_to_datetime(value)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return max(0, int((parsed - datetime.now(timezone.utc)).total_seconds()))
        except (TypeError, ValueError, OverflowError):
            return None
