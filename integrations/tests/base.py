from unittest import mock

from django.core.cache import cache
from django.test import SimpleTestCase, override_settings
from rest_framework.test import APIRequestFactory, force_authenticate

from .fakes import TEST_SETTINGS


@override_settings(**TEST_SETTINGS)
class IntegrationTestCase(SimpleTestCase):
    """SimpleTestCase: any database query fails the test, so these never touch react_database."""

    factory = APIRequestFactory()

    def setUp(self):
        cache.clear()
        # Audit entries would be database writes: captured instead.
        self.audit = mock.patch("integrations.api.record").start()
        self.denied_audit = mock.patch("jira.api.record").start()
        mock.patch("integrations.api._app_versions", return_value=["11.1", "10.9", "10.8"]).start()
        mock.patch("integrations.http.time.sleep").start()
        # The admin's branch / fix version scope (a database table): empty unless a test sets it.
        self.scope = {"branches": {}, "fixVersions": [], "jiraProjects": [], "versionStarts": {}, "entries": []}
        mock.patch("integrations.scope.current", side_effect=lambda: self.scope).start()
        self.jira_projects = []  # projects admins added on top of JIRA_PROJECT_KEYS
        mock.patch("integrations.scope.jira_projects", side_effect=lambda: self.jira_projects).start()
        # Connection settings saved on Settings → Integrations (a database table): none, so .env (TEST_SETTINGS) applies.
        self.saved_credentials = {}
        mock.patch("integrations.credentials.stored", side_effect=lambda: self.saved_credentials).start()
        self.repository_changes = ([], [])  # (added, removed .env repositories)
        mock.patch("integrations.scope.repository_changes", side_effect=lambda: self.repository_changes).start()
        self.addCleanup(mock.patch.stopall)

    def serve(self, http):
        """Every outgoing HTTP request goes to `http` (a FakeHttp) for the rest of the test."""
        mock.patch("urllib.request.urlopen", http).start()
        self.http = http
        return http

    def call(self, view, user=None, *, method="get", path="/api/x", data=None, **kwargs):
        request = getattr(self.factory, method)(path, data or {}, format="json" if method != "get" else None)
        if user is not None:
            force_authenticate(request, user=user)
        return view(request, **kwargs)
