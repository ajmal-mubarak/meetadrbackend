"""Test Suite for Container Health Probe and OpenAPI Documentation (Phase 11 - Scopes D & E)."""
from unittest.mock import patch
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient


class HealthCheckAndDocumentationAPITests(TestCase):
    """Integration test suite for /api/v1/health/, /api/schema/, /api/docs/, and /api/redoc/."""

    def setUp(self):
        self.client = APIClient()

    # =========================================================================
    # HEALTH CHECK TESTS — GET /api/v1/health/
    # =========================================================================

    def test_01_health_endpoint_is_publicly_accessible(self):
        """1. Health check is accessible anonymously without credentials."""
        response = self.client.get('/api/v1/health/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_02_healthy_system_returns_proper_envelope(self):
        """2. Healthy database returns status healthy, database connected, and timestamp."""
        response = self.client.get('/api/v1/health/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data.get('status'), 'healthy')
        self.assertEqual(response.data.get('database'), 'connected')
        self.assertIn('timestamp', response.data)

    def test_03_database_failure_returns_503_without_leaking_internals(self):
        """3. Database connection failure returns 503 without leaking stack traces or credentials."""
        with patch('django.db.connection.ensure_connection', side_effect=Exception("Database connection timeout")):
            response = self.client.get('/api/v1/health/')
            self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
            self.assertEqual(response.data.get('status'), 'unhealthy')
            self.assertEqual(response.data.get('database'), 'disconnected')
            self.assertIn('timestamp', response.data)

            # Strict check: ensure internal error message or stack trace is not exposed
            resp_str = str(response.data).lower()
            self.assertNotIn("timeout", resp_str)
            self.assertNotIn("exception", resp_str)
            self.assertNotIn("traceback", resp_str)
            self.assertNotIn("password", resp_str)

    # =========================================================================
    # OPENAPI 3.0 & DOCUMENTATION TESTS
    # =========================================================================

    def test_04_schema_endpoint_responds_successfully(self):
        """4. GET /api/schema/ generates valid OpenAPI 3.0 YAML/JSON specification."""
        response = self.client.get('/api/schema/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_05_swagger_ui_endpoint_responds_successfully(self):
        """5. GET /api/docs/ returns interactive Swagger UI."""
        response = self.client.get('/api/docs/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn(b'swagger-ui', response.content.lower())

    def test_06_redoc_ui_endpoint_responds_successfully(self):
        """6. GET /api/redoc/ returns interactive ReDoc documentation UI."""
        response = self.client.get('/api/redoc/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn(b'redoc', response.content.lower())

    def test_07_generated_schema_contains_phase_11_endpoints(self):
        """7. Generated schema includes admin doctors, bookings, reports, and health endpoints."""
        response = self.client.get('/api/schema/?format=json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        schema = response.json()

        paths = schema.get('paths', {})
        self.assertIn('/api/v1/health/', paths)
        self.assertIn('/api/v1/admin/doctors/', paths)
        self.assertIn('/api/v1/admin/doctors/{id}/status/', paths)
        self.assertIn('/api/v1/admin/bookings/', paths)
        self.assertIn('/api/v1/admin/bookings/{id}/cancel/', paths)
        self.assertIn('/api/v1/admin/reports/', paths)

    def test_08_schema_documents_jwt_bearer_authentication(self):
        """8. Generated schema documents BearerAuth security scheme."""
        response = self.client.get('/api/schema/?format=json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        schema = response.json()

        components = schema.get('components', {})
        security_schemes = components.get('securitySchemes', {})
        self.assertIn('BearerAuth', security_schemes)
        self.assertEqual(security_schemes['BearerAuth'].get('scheme'), 'bearer')
