"""Audit log CSV export and the health check (no database)."""
from unittest import mock

from django.db import DatabaseError
from django.test import SimpleTestCase
from rest_framework.test import APIRequestFactory

from audit.api import _csv_cell
from config.health import health


class CsvCellTests(SimpleTestCase):
    def test_formula_cells_are_neutralised(self):
        for value in ("=HYPERLINK(\"x\")", "+1", "-1", "@SUM(A1)", "\tx"):
            self.assertTrue(_csv_cell(value).startswith("'"), value)

    def test_plain_values_are_unchanged(self):
        self.assertEqual(_csv_cell("Mozilla/5.0"), "Mozilla/5.0")
        self.assertEqual(_csv_cell(None), "")
        self.assertEqual(_csv_cell(42), "42")


class HealthTests(SimpleTestCase):
    factory = APIRequestFactory()

    def test_ok(self):
        with mock.patch("config.health.connection") as connection:
            response = health(self.factory.get("/api/health"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, {"status": "ok", "database": "ok"})
        connection.cursor.return_value.__enter__.return_value.execute.assert_called_once_with("SELECT 1")

    def test_database_down_is_503_without_details(self):
        with mock.patch("config.health.connection") as connection:
            connection.cursor.side_effect = DatabaseError("Access denied for user 'root'")
            with self.assertLogs("config.health", "ERROR"):
                response = health(self.factory.get("/api/health"))
        self.assertEqual(response.status_code, 503)
        self.assertNotIn("root", str(response.data))
