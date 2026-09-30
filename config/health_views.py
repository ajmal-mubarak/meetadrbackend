"""Container and Orchestrator Health Check Views."""
from django.db import connection
from django.utils import timezone
from rest_framework import views, status
from rest_framework.response import Response
from rest_framework.permissions import AllowAny


class HealthCheckView(views.APIView):
    """
    Public lightweight container & orchestrator health check probe.
    GET /api/v1/health/
    
    Security & Privacy Invariant:
    Never exposes database credentials, hostnames, environment variables,
    or internal stack traces on failure.
    """
    permission_classes = [AllowAny]

    def get(self, request):
        db_status = "connected"
        http_status = status.HTTP_200_OK
        overall_status = "healthy"

        try:
            connection.ensure_connection()
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1;")
                cursor.fetchone()
        except Exception:
            overall_status = "unhealthy"
            db_status = "disconnected"
            http_status = status.HTTP_503_SERVICE_UNAVAILABLE

        return Response({
            "status": overall_status,
            "database": db_status,
            "timestamp": timezone.now().isoformat(),
        }, status=http_status)
