import logging

from rest_framework.response import Response
from rest_framework.views import exception_handler

from trip_planner.services.errors import TripPlannerError

LOGGER = logging.getLogger(__name__)


def api_exception_handler(exc, context):
    if isinstance(exc, TripPlannerError):
        return Response({"error": {"code": exc.code, "message": exc.message}}, status=exc.status_code)
    response = exception_handler(exc, context)
    if response is not None:
        detail = response.data
        return Response({"error": {"code": "validation_error", "message": "The request is invalid.", "details": detail}}, status=response.status_code)
    LOGGER.error("Unhandled API exception", exc_info=(type(exc), exc, exc.__traceback__))
    return Response({"error": {"code": "internal_error", "message": "An unexpected error occurred."}}, status=500)
