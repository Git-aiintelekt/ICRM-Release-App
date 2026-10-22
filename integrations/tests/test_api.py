"""Authorization, status/refresh, and the dashboard (MOCKED external responses)."""
from unittest import mock

from django.test import override_settings

from audit import models as audit
from integrations import api

from .base import IntegrationTestCase
from .fakes import SECRETS, FakeHttp, FakeUser, jira_server
from .test_bitbucket import bitbucket_and_jira
from .test_jira import counts_by_jql

ADMIN = FakeUser(admin=True)
VIEWER = FakeUser(jira=True)
PLAIN = FakeUser()

READ_VIEWS = [
    (api.status, {}), (api.dashboard, {}), (api.jira_filters, {}), (api.jira_summary, {}), (api.jira_issues, {}),
    (api.jira_releases, {}), (api.bitbucket_repositories, {}),
    (api.bitbucket_branches, {"slug": "icrm-base-framework-master"}),
    (api.bitbucket_commits, {"slug": "icrm-base-framework-master"}),
    (api.bitbucket_pull_requests, {"slug": "icrm-base-framework-master"}),
]


class AuthorizationTests(IntegrationTestCase):
    def setUp(self):
        super().setUp()
        self.serve(FakeHttp())  # nothing may reach Jira/Bitbucket for a refused request

    def test_signed_out_gets_401(self):
        for view, kwargs in READ_VIEWS:
            self.assertEqual(self.call(view, None, **kwargs).status_code, 401, view.__name__)
        self.assertEqual(self.call(api.refresh, None, method="post").status_code, 401)

    def test_user_without_jira_access_gets_403_and_is_audited(self):
        for view, kwargs in READ_VIEWS:
            self.assertEqual(self.call(view, PLAIN, **kwargs).status_code, 403, view.__name__)
        self.assertEqual(self.denied_audit.call_count, len(READ_VIEWS))
        self.assertEqual(self.denied_audit.call_args.args[1], audit.JIRA_ACCESS_DENIED)
        self.assertEqual(self.http.calls, [])

    def test_viewer_cannot_refresh(self):
        self.assertEqual(self.call(api.refresh, VIEWER, method="post").status_code, 403)

    def test_viewer_can_read_status(self):
        self.assertEqual(self.call(api.status, VIEWER).status_code, 200)


class StatusTests(IntegrationTestCase):
    def test_status_shows_configuration_but_never_secrets(self):
        body = self.call(api.status, VIEWER).data
        self.assertTrue(body["jira"]["configured"])
        self.assertEqual(body["jira"]["projectKeys"], ["CS", "IBP", "CT", "CP"])
        self.assertEqual(body["bitbucket"]["repositories"], ["icrm-base-framework-master"])
        text = str(body)
        for secret in SECRETS + ("bot@example.test",):
            self.assertNotIn(secret, text)

    @override_settings(JIRA_BASE_URL="", JIRA_EMAIL="", JIRA_API_TOKEN="", BITBUCKET_EMAIL="", BITBUCKET_API_TOKEN="")
    def test_status_lists_missing_settings(self):
        body = self.call(api.status, VIEWER).data
        self.assertFalse(body["jira"]["configured"])
        self.assertEqual(body["jira"]["missingSettings"], ["JIRA_BASE_URL", "JIRA_EMAIL", "JIRA_API_TOKEN"])
        self.assertFalse(body["bitbucket"]["configured"])

    def test_added_projects_follow_the_env_ones(self):
        self.jira_projects[:] = ["NEWP", "CS", "bad key"]
        body = self.call(api.status, VIEWER).data["jira"]
        self.assertEqual(body["projectKeys"], ["CS", "IBP", "CT", "CP", "NEWP"])
        self.assertEqual(body["baseProjectKeys"], ["CS", "IBP", "CT", "CP"])

    def test_invalid_project_keys_are_ignored(self):
        with override_settings(JIRA_PROJECT_KEYS=["CS", "cs) OR (1", ""]):
            self.assertEqual(self.call(api.status, VIEWER).data["jira"]["projectKeys"], ["CS"])

    def test_refresh_invalidates_cache_checks_services_and_is_audited(self):
        http = self.serve(bitbucket_and_jira())
        http.on("POST", r"/search/approximate-count", counts_by_jql)
        http.routes.insert(0, http.routes.pop())
        self.call(api.jira_summary, VIEWER)
        before = len(http.calls)
        body = self.call(api.refresh, ADMIN, method="post").data
        self.assertEqual(body["checks"]["jira"], {"ok": True, "account": "Release bot"})
        self.assertEqual(body["checks"]["bitbucket"], {"ok": True, "repository": "acme/icrm-base-framework-master"})
        self.assertIsNotNone(body["jira"]["lastSuccessAt"])
        self.call(api.jira_summary, VIEWER)
        self.assertGreater(len([c for c in http.calls[before:] if "approximate-count" in c["path"]]), 0)  # re-fetched
        self.assertEqual(self.audit.call_args.args[1], audit.INTEGRATION_REFRESH)
        self.assertEqual(self.audit.call_args.kwargs["details"], "jira: ok; bitbucket: ok")

    def test_refresh_reports_failures(self):
        http = jira_server()
        http.on("GET", r"/rest/api/3/myself", (401, {}))
        http.routes.insert(0, http.routes.pop())
        self.serve(http)
        with override_settings(BITBUCKET_WORKSPACE=""):
            body = self.call(api.refresh, ADMIN, method="post").data
        self.assertFalse(body["checks"]["jira"]["ok"])
        self.assertIn("rejected the credentials", body["checks"]["jira"]["detail"])
        self.assertEqual(body["checks"]["bitbucket"], {"ok": False, "detail": "Not configured."})
        self.assertEqual(self.audit.call_args.kwargs["details"], "jira: failed; bitbucket: not configured")
        self.assertIsNotNone(body["jira"]["lastErrorAt"])


class DashboardTests(IntegrationTestCase):
    def test_dashboard_combines_every_section(self):
        http = self.serve(bitbucket_and_jira())
        http.on("POST", r"/search/approximate-count", counts_by_jql)
        http.routes.insert(0, http.routes.pop())
        body = self.call(api.dashboard, VIEWER).data
        self.assertEqual(body["jiraSummary"]["data"]["issues"]["open"], 40)
        self.assertEqual(body["jiraSummary"]["data"]["bugs"]["open"], 12)
        self.assertEqual(body["releaseBranches"]["data"], [])  # nothing published from a release branch
        self.assertEqual(set(body), {"jiraSummary", "releaseBranches", "status"})
        # A second load is served from the cache: no new external calls.
        calls = len(http.calls)
        self.call(api.dashboard, VIEWER)
        self.assertEqual(len(http.calls), calls)

    def test_dashboard_follows_the_scope(self):
        self.scope.update(fixVersions=["iCRM 10.9"], branches={"icrm-base-framework-master": ["icrm_release_10_9_0"]})
        http = self.serve(bitbucket_and_jira())
        http.on("POST", r"/search/approximate-count", counts_by_jql)
        http.routes.insert(0, http.routes.pop())
        body = self.call(api.dashboard, VIEWER).data
        self.assertEqual(body["jiraSummary"]["data"]["fixVersions"], ["iCRM 10.9"])
        self.assertTrue(all('fixVersion in ("iCRM 10.9")' in b["jql"] for b in http.bodies("approximate-count")))
        self.assertEqual(body["status"]["scope"]["fixVersions"], ["iCRM 10.9"])
        self.assertFalse([c for c in http.calls if c["path"].endswith(("/commits", "/pullrequests"))])

    @override_settings(JIRA_API_TOKEN="", BITBUCKET_WORKSPACE="")
    def test_dashboard_when_nothing_is_configured(self):
        self.serve(FakeHttp())
        body = self.call(api.dashboard, VIEWER).data
        self.assertTrue(body["jiraSummary"]["notConfigured"])
        self.assertTrue(body["releaseBranches"]["notConfigured"])
        self.assertEqual(self.http.calls, [])


class ScopeAdminTests(IntegrationTestCase):
    """Only admins change the scope; names are checked against Jira / Bitbucket before they're saved."""

    def setUp(self):
        super().setUp()
        self.rows = mock.patch("integrations.api.IntegrationScope").start()
        self.rows.objects.filter.return_value.exists.return_value = False
        self.serve(bitbucket_and_jira())

    def add(self, user, **data):
        return self.call(api.scope_add, user, method="post", data=data)

    def test_viewers_cannot_change_the_scope(self):
        self.assertEqual(self.add(VIEWER, kind="FIX_VERSION", value="iCRM 10.9").status_code, 403)
        self.rows.objects.create.assert_not_called()

    def test_existing_branch_is_added_and_audited(self):
        response = self.add(ADMIN, kind="BRANCH", repository="icrm-base-framework-master", value="icrm_release_10_9_0")
        self.assertEqual(response.status_code, 201)
        self.rows.objects.create.assert_called_once()
        self.assertEqual(self.audit.call_args.args[1], audit.INTEGRATION_SCOPE)

    def test_unknown_names_and_repositories_are_refused(self):
        self.http.on("GET", r"/refs/branches", {"values": []})
        self.http.routes.insert(0, self.http.routes.pop())
        self.assertEqual(self.add(ADMIN, kind="BRANCH", repository="icrm-base-framework-master", value="nope").status_code, 400)
        self.assertEqual(self.add(ADMIN, kind="BRANCH", repository="other-repo", value="master").status_code, 400)
        self.assertEqual(self.add(ADMIN, kind="FIX_VERSION", value="No such version").status_code, 400)
        self.rows.objects.create.assert_not_called()

    def test_jira_project_is_checked_then_added(self):
        self.http.on("GET", r"/rest/api/3/project/NEWP", {"key": "NEWP"})
        self.http.on("GET", r"/rest/api/3/project/GONE", (404, {"errorMessages": ["No project"]}))
        self.assertEqual(self.add(ADMIN, kind="JIRA_PROJECT", value="newp").status_code, 201)
        self.assertEqual(self.rows.objects.create.call_args.kwargs["value"], "NEWP")
        self.assertEqual(self.add(ADMIN, kind="JIRA_PROJECT", value="GONE").status_code, 400)
        self.assertEqual(self.add(ADMIN, kind="JIRA_PROJECT", value="CS").status_code, 400)  # already in .env
        self.assertEqual(self.add(ADMIN, kind="JIRA_PROJECT", value="cs) OR (1").status_code, 400)
        self.rows.objects.create.assert_called_once()

    def test_repository_is_checked_then_added(self):
        self.rows.objects.filter.return_value.first.return_value = None
        self.http.on("GET", r"/repositories/acme/new-repo", {"slug": "new-repo", "full_name": "acme/new-repo"})
        self.http.on("GET", r"/repositories/acme/gone", (404, {"error": {"message": "Repository not found"}}))
        self.assertEqual(self.add(ADMIN, kind="REPOSITORY", value="new-repo").status_code, 201)
        self.assertEqual(self.rows.objects.create.call_args.kwargs, {"kind": "REPOSITORY", "value": "new-repo", "added_by": ADMIN})
        self.assertEqual(self.add(ADMIN, kind="REPOSITORY", value="gone").status_code, 400)
        self.assertEqual(self.add(ADMIN, kind="REPOSITORY", value="icrm-base-framework-master").status_code, 400)  # listed
        self.assertEqual(self.add(ADMIN, kind="REPOSITORY", value="a/b").status_code, 400)
        self.rows.objects.create.assert_called_once()

    def test_a_version_start_date_replaces_the_old_one(self):
        self.assertEqual(self.add(ADMIN, kind="VERSION_START", repository="10.9", value="2025-11-03").status_code, 201)
        self.rows.objects.filter.assert_any_call(kind="VERSION_START", repository="10.9")
        self.rows.objects.filter.return_value.delete.assert_called()
        self.assertEqual(self.rows.objects.create.call_args.kwargs["value"], "2025-11-03")
        self.assertEqual(self.add(ADMIN, kind="VERSION_START", repository="9.9", value="2025-11-03").status_code, 400)
        self.assertEqual(self.add(ADMIN, kind="VERSION_START", repository="10.9", value="Nov 2025").status_code, 400)

    def test_the_last_repository_cannot_be_removed(self):
        response = self.add(ADMIN, kind="REPOSITORY_HIDDEN", value="icrm-base-framework-master")
        self.assertEqual(response.status_code, 400)
        self.assertIn("At least one repository", str(response.data))
        self.repository_changes = (["new-repo"], [])
        self.assertEqual(self.add(ADMIN, kind="REPOSITORY_HIDDEN", value="icrm-base-framework-master").status_code, 201)
        self.assertEqual(self.add(ADMIN, kind="REPOSITORY_HIDDEN", value="new-repo").status_code, 400)  # not from .env
