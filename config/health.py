"""/api/health: for the reverse proxy and uptime monitors. Public, says only whether the app and its database answer."""
import logging

from django.db import DatabaseError, connection
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

log = logging.getLogger(__name__)


@api_view(["GET"])
def health(request):
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except DatabaseError as exc:
        # The reason goes to the server log only: a public endpoint shouldn't describe the database.
        log.error("Health check: database unavailable: %s: %s", type(exc).__name__, exc)
        return Response({"status": "error", "database": "unavailable"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
    return Response({"status": "ok", "database": "ok"})
