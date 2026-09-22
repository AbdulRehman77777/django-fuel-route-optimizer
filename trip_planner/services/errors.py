class TripPlannerError(Exception):
    code = "trip_planner_error"
    status_code = 400

    def __init__(self, message=None):
        super().__init__(message or "Unable to plan this trip.")
        self.message = message or "Unable to plan this trip."


class ConfigurationError(TripPlannerError):
    code = "service_not_configured"
    status_code = 503


class LocationNotFoundError(TripPlannerError):
    code = "location_not_found"
    status_code = 422


class LocationOutsideUSError(TripPlannerError):
    code = "location_outside_usa"
    status_code = 422


class ProviderUnavailableError(TripPlannerError):
    code = "routing_provider_unavailable"
    status_code = 503


class ProviderRateLimitError(TripPlannerError):
    code = "routing_provider_rate_limited"
    status_code = 503


class ProviderRequestError(TripPlannerError):
    code = "routing_provider_rejected_request"
    status_code = 502


class MalformedProviderResponseError(TripPlannerError):
    code = "malformed_provider_response"
    status_code = 502


class RouteNotFoundError(TripPlannerError):
    code = "route_not_found"
    status_code = 422


class FuelDataMissingError(TripPlannerError):
    code = "fuel_data_not_imported"
    status_code = 503


class NoFeasibleRouteError(TripPlannerError):
    code = "no_feasible_fuel_plan"
    status_code = 422
