"""Jira (MOCKED responses): counts, bug filtering, search, pagination, release summaries, failures."""
import re
from unittest import mock

from django.test import override_settings

from integrations import api
from integrations.jira_client import JiraClient, parse_fix_version_map

from .base import IntegrationTestCase
from .fakes import SECRETS, FakeUser, jira_issue, jira_server

VIEWER = FakeUser(jira=True)


def counts_by_jql(call):
    """Answers each count query from the JQL clauses it contains (not hardcoded per card)."""
    jql = call["body"]["jql"]
    bug = 'issuetype in ("Bug")' in jql
    if "statusCategory != Done" in jql:
        n = 12 if bug else 40
    elif 'status in ("Resolved")' in jql:
        n = 5 if bug else 25
    elif 'status in ("Closed", "Done")' in jql:
        n = 3 if bug else 30
    elif "statusCategory = Done" in jql:
        n = 9 if bug else 60
    else:
        n = 21 if bug else 100
    return {"count": n}


class JiraCountsTests(IntegrationTestCase):
    def test_summary_counts_open_done_resolved_closed_and_bugs(self):
        self.serve(jira_server(count=counts_by_jql))
        body = self.call(api.jira_summary, VIEWER).data
        self.assertEqual(body["issues"], {"total": 100, "open": 40, "done": 60, "resolved": 25, "closed": 30, "doneOther": 5})
        self.assertEqual(body["bugs"], {"total": 21, "open": 12, "done": 9, "resolved": 5, "closed": 3, "doneOther": 1})
        self.assertEqual(body["definitions"]["closedStatuses"], ["Closed", "Done"])
        self.assertTrue(body["approximate"])
        jqls = [b["jql"] for b in self.http.bodies("approximate-count")]
        self.assertTrue(all(j.startswith("project in (CS, IBP, CT, CP)") for j in jqls))
        # Resolved and Closed are both restricted to the Done category, never inferred from anything else.
        self.assertIn('project in (CS, IBP, CT, CP) AND statusCategory = Done AND status in ("Resolved")', jqls)

    def test_counts_are_cached_between_requests(self):
        self.serve(jira_server(count=counts_by_jql))
        self.call(api.jira_summary, VIEWER)
        calls = len(self.http.calls)
        self.call(api.jira_summary, VIEWER)
        self.assertEqual(len(self.http.calls), calls)

    @override_settings(JIRA_RESOLVED_STATUSES=["Resolved", "Fixed"], JIRA_BUG_ISSUE_TYPES=["Defect"])
    def test_configured_names_missing_from_jira_are_left_out_of_jql_and_reported(self):
        self.serve(jira_server(count=counts_by_jql))
        body = self.call(api.jira_summary, VIEWER).data
        self.assertIsNone(body["bugs"])
        self.assertTrue(any("Fixed" in w for w in body["warnings"]))
        self.assertTrue(any("Defect" in w for w in body["warnings"]))
        self.assertFalse(any("Fixed" in b["jql"] or "Defect" in b["jql"] for b in self.http.bodies("approximate-count")))

    def test_missing_project_is_reported_and_others_still_counted(self):
        self.serve(jira_server(count=counts_by_jql, missing_projects=("CP",)))
        body = self.call(api.jira_summary, VIEWER).data
        self.assertEqual(body["projects"], ["CS", "IBP", "CT"])
        self.assertTrue(any("CP" in w for w in body["warnings"]))

    def test_summary_for_fix_version(self):
        self.serve(jira_server(count=counts_by_jql))
        self.call(api.jira_summary, VIEWER, path="/x?fixVersion=iCRM+10.9")
        self.assertTrue(all('fixVersion in ("iCRM 10.9")' in b["jql"] for b in self.http.bodies("approximate-count")))


class JiraScopeTests(IntegrationTestCase):
    """With fix versions chosen by an admin, counts and lists cover only those versions."""

    def setUp(self):
        super().setUp()
        self.scope["fixVersions"] = ["iCRM 10.9", "10.8.5"]
        self.serve(jira_server(count=counts_by_jql))

    def test_counts_default_to_the_scope(self):
        body = self.call(api.jira_summary, VIEWER).data
        self.assertEqual(body["fixVersions"], ["iCRM 10.9", "10.8.5"])
        self.assertTrue(all('fixVersion in ("iCRM 10.9", "10.8.5")' in b["jql"] for b in self.http.bodies("approximate-count")))

    def test_one_version_of_the_scope(self):
        self.call(api.jira_summary, VIEWER, path="/x?fixVersion=10.8.5")
        self.assertTrue(all('fixVersion in ("10.8.5")' in b["jql"] for b in self.http.bodies("approximate-count")))

    def test_a_version_outside_the_scope_is_refused(self):
        for view in (api.jira_summary, api.jira_issues):
            response = self.call(view, VIEWER, path="/x?fixVersion=11.0")
            self.assertEqual(response.status_code, 400)
        self.assertEqual(self.http.bodies("approximate-count"), [])


class JiraIssueListTests(IntegrationTestCase):
    def setUp(self):
        super().setUp()

        def search(call):
            if call["body"].get("nextPageToken") == "page-2":
                return {"issues": [jira_issue("CS-3")], "isLast": True}
            return {"issues": [jira_issue("CS-1", issue_type="Bug", assignee=None, priority=None),
                               jira_issue("CT-2", status="Resolved", category="done")], "nextPageToken": "page-2", "isLast": False}

        self.serve(jira_server(search=search, count=lambda call: {"count": 3}))

    def test_list_fields_and_missing_fields(self):
        body = self.call(api.jira_issues, VIEWER).data
        first, second = body["issues"]
        self.assertEqual(first["key"], "CS-1")
        self.assertEqual(first["issueType"], "Bug")
        self.assertIsNone(first["assignee"])
        self.assertIsNone(first["priority"])
        self.assertEqual(first["url"], "https://jira.test/browse/CS-1")
        self.assertEqual(second["statusCategory"], "done")
        self.assertEqual(body["total"], 3)
        self.assertEqual(body["nextPageToken"], "page-2")
        self.assertFalse(body["isLast"])

    def test_release_lists_only_its_own_jira_issues(self):
        mock.patch("integrations.api.ReleaseVersion.objects.filter").start().return_value.exists.return_value = True
        items = mock.patch("integrations.api.ReleaseItem.objects.filter").start()
        items.return_value.exclude.return_value.exclude.return_value.values_list.return_value = ["CS-1", "cs-9", "CT-2"]
        mock.patch("integrations.jira_client.JiraClient.issue_statuses",
                   return_value={"CS-1": {}, "CT-2": {}}).start()  # CS-9 isn't visible in Jira
        body = self.call(api.jira_issues, VIEWER, path="/x?release=10.9.0").data
        sent = self.http.bodies("search/jql")[-1]["jql"]
        self.assertIn('key in ("CS-1", "CT-2")', sent)
        self.assertNotIn("CS-9", sent)
        self.assertIn("key in (the 2 issues of 10.9.0)", body["jql"])

    def test_release_with_no_visible_issues_matches_nothing_and_unknown_release_is_refused(self):
        found = mock.patch("integrations.api.ReleaseVersion.objects.filter").start().return_value
        found.exists.return_value = True
        mock.patch("integrations.api.ReleaseItem.objects.filter").start() \
            .return_value.exclude.return_value.exclude.return_value.values_list.return_value = []
        mock.patch("integrations.jira_client.JiraClient.issue_statuses", return_value={}).start()
        self.call(api.jira_issues, VIEWER, path="/x?release=10.9.0")
        self.assertIn("key is EMPTY", self.http.bodies("search/jql")[-1]["jql"])
        found.exists.return_value = False
        self.assertEqual(self.call(api.jira_issues, VIEWER, path="/x?release=9.9").status_code, 400)

    def test_next_page_uses_token(self):
        body = self.call(api.jira_issues, VIEWER, path="/x?pageToken=page-2&limit=10").data
        self.assertEqual([i["key"] for i in body["issues"]], ["CS-3"])
        self.assertTrue(body["isLast"])
        sent = self.http.bodies("search/jql")[-1]
        self.assertEqual(sent["nextPageToken"], "page-2")
        self.assertEqual(sent["maxResults"], 10)

    def test_bug_filter(self):
        body = self.call(api.jira_issues, VIEWER, path="/x?state=bug").data
        self.assertIn('issuetype in ("Bug")', body["jql"])

    def test_open_and_closed_filters(self):
        self.assertIn("statusCategory != Done", self.call(api.jira_issues, VIEWER, path="/x?state=open").data["jql"])
        jql = self.call(api.jira_issues, VIEWER, path="/x?state=closed").data["jql"]
        self.assertIn('statusCategory = Done AND status in ("Closed", "Done")', jql)

    def test_type_status_version_filters_are_quoted(self):
        jql = self.call(api.jira_issues, VIEWER, path='/x?type=Story&status=In+Progress&fixVersion=10.9"+OR+1=1').data["jql"]
        self.assertIn('issuetype in ("Story")', jql)
        self.assertIn('status in ("In Progress")', jql)
        self.assertIn('fixVersion in ("10.9\\" OR 1=1")', jql)

    def test_search_by_key_and_text(self):
        self.assertIn('key = "CS-12"', self.call(api.jira_issues, VIEWER, path="/x?q=cs-12").data["jql"])
        jql = self.call(api.jira_issues, VIEWER, path="/x?createdFrom=2025-11-01&createdTo=2025-12-18").data["jql"]
        self.assertIn('created >= "2025-11-01" AND created < "2025-12-19"', jql)
        self.assertEqual(self.call(api.jira_issues, VIEWER, path="/x?createdFrom=2025-12-18&createdTo=2025-11-01").status_code, 400)
        self.assertEqual(self.call(api.jira_issues, VIEWER, path='/x?createdFrom=2025-11-01"+OR+1=1').status_code, 400)
        jql = self.call(api.jira_issues, VIEWER, path='/x?q=login+"timeout"+(prod)').data["jql"]
        self.assertIn('text ~ "login timeout prod"', jql)

    def test_invalid_parameters_are_rejected(self):
        for query in ("state=nope", "limit=500", "pageToken=bad%20token", "q=" + "x" * 201):
            self.assertEqual(self.call(api.jira_issues, VIEWER, path=f"/x?{query}").status_code, 400, query)


class JiraReleaseSummaryTests(IntegrationTestCase):
    VERSIONS = [
        {"name": "iCRM 10.9", "project": "CS", "released": True, "archived": False, "releaseDate": "2025-12-18"},
        {"name": "10.8.5", "project": "IBP", "released": True, "archived": False, "releaseDate": "2025-10-08"},
        {"name": "Old", "project": "CS", "released": True, "archived": True, "releaseDate": "2020-01-01"},
    ]

    def setUp(self):
        super().setUp()

        def search(call):
            if call["body"].get("nextPageToken") == "p2":
                return {"issues": [jira_issue("CS-3", fix_versions=["10.8.5"], issue_type="Bug")], "isLast": True}
            return {"issues": [
                jira_issue("CS-1", fix_versions=["iCRM 10.9"], issue_type="Bug"),
                jira_issue("CS-2", fix_versions=["iCRM 10.9"], status="Resolved", category="done"),
                jira_issue("CS-4", fix_versions=["iCRM 10.9", "10.8.5"], status="Closed", category="done"),
            ], "nextPageToken": "p2", "isLast": False}

        self.serve(jira_server(versions=self.VERSIONS, search=search))

    def test_without_map_rows_use_jira_names_and_matches_are_only_candidates(self):
        body = self.call(api.jira_releases, VIEWER).data
        self.assertFalse(body["mapped"])
        self.assertEqual([r["label"] for r in body["rows"]], ["iCRM 10.9", "10.8.5"])  # archived left out
        self.assertIsNone(body["rows"][0]["appVersion"])
        self.assertEqual(body["rows"][0]["counts"], {"total": 3, "open": 1, "done": 2, "resolved": 1, "closed": 1, "bugs": 1, "openBugs": 1})
        self.assertEqual(body["rows"][1]["counts"]["total"], 2)
        # Name matches are hints for writing JIRA_FIX_VERSION_MAP, never used as the mapping itself.
        self.assertEqual(body["candidates"], {"10.9": ["iCRM 10.9"], "10.8": ["10.8.5"]})

    @override_settings(JIRA_FIX_VERSION_MAP="10.9=iCRM 10.9|10.9.1; 10.8=10.8.5")
    def test_with_map_rows_are_app_versions_and_missing_names_warned(self):
        body = self.call(api.jira_releases, VIEWER).data
        self.assertTrue(body["mapped"])
        self.assertEqual([(r["label"], r["fixVersions"]) for r in body["rows"]], [("10.9", ["iCRM 10.9"]), ("10.8", ["10.8.5"])])
        self.assertTrue(any("10.9.1" in w for w in body["warnings"]))
        self.assertEqual(body["candidates"], {})

    def test_candidate_match_respects_number_boundaries(self):
        from unittest import mock
        with mock.patch("integrations.api._app_versions", return_value=["10.1", "0.9"]):
            self.assertEqual(self.call(api.jira_releases, VIEWER).data["candidates"], {})  # not "10.10", not "10.9"

    @override_settings(JIRA_FIX_VERSION_MAP="10.9=iCRM 10.9")
    def test_scope_rows_are_only_the_chosen_fix_versions(self):
        self.scope["fixVersions"] = ["10.8.5", "Gone"]
        body = self.call(api.jira_releases, VIEWER).data
        self.assertEqual([r["label"] for r in body["rows"]], ["10.8.5"])  # the scope wins over the map
        self.assertEqual(body["rows"][0]["counts"]["total"], 2)
        self.assertTrue(any("Gone" in w for w in body["warnings"]))
        self.assertEqual(body["candidates"], {})

    def test_parse_fix_version_map(self):
        self.assertEqual(parse_fix_version_map(" 10.9 = A | B ;bad; 10.8=C"), {"10.9": ["A", "B"], "10.8": ["C"]})


class JiraFailureTests(IntegrationTestCase):
    def failing(self, status, payload=None, headers=None):
        http = jira_server()
        http.routes.insert(0, ("GET", re.compile(r"/statuses$"), (status, payload or {}, headers or {})))
        return self.serve(http)

    def assert_safe(self, response):
        text = str(response.data)
        for secret in SECRETS:
            self.assertNotIn(secret, text)

    def test_bad_credentials(self):
        self.failing(401)
        response = self.call(api.jira_summary, VIEWER)
        self.assertEqual(response.status_code, 502)
        self.assertIn("rejected the credentials", response.data["detail"])
        self.assert_safe(response)

    def test_forbidden(self):
        self.failing(403)
        response = self.call(api.jira_summary, VIEWER)
        self.assertEqual(response.status_code, 502)
        self.assertIn("denied access", response.data["detail"])

    def test_rate_limited_long_wait_is_reported(self):
        self.failing(429, headers={"Retry-After": "120"})
        response = self.call(api.jira_summary, VIEWER)
        self.assertEqual(response.status_code, 503)
        self.assertIn("rate limiting", response.data["detail"])

    def test_rate_limited_short_wait_is_retried_once(self):
        attempts = []

        def flaky(call):
            attempts.append(1)
            return (429, {}, {"Retry-After": "1"}) if len(attempts) == 1 else []

        http = jira_server(count=lambda call: {"count": 1})
        http.routes.insert(0, ("GET", re.compile(r"/CS/statuses$"), flaky))
        self.serve(http)
        self.assertEqual(self.call(api.jira_summary, VIEWER).status_code, 200)
        self.assertEqual(len(attempts), 2)

    def test_server_error_and_timeout(self):
        self.failing(500)
        self.assertEqual(self.call(api.jira_summary, VIEWER).status_code, 502)
        from django.core.cache import cache
        cache.clear()
        http = jira_server()
        http.routes.insert(0, ("GET", re.compile(r"/statuses$"), TimeoutError("timed out")))
        self.serve(http)
        response = self.call(api.jira_summary, VIEWER)
        self.assertEqual(response.status_code, 502)
        self.assertIn("Could not reach Jira", response.data["detail"])

    def test_error_marks_health_and_is_not_cached(self):
        self.failing(500)
        self.call(api.jira_summary, VIEWER)
        status = self.call(api.status, VIEWER).data["jira"]
        self.assertIsNotNone(status["lastErrorAt"])
        self.assertIsNone(status["lastSuccessAt"])

    def test_bad_jql_value_is_400(self):
        http = jira_server()
        http.on("POST", r"/search/jql", (400, {"errorMessages": ["The value 'Nope' does not exist for the field 'fixVersion'."]}))
        http.routes.insert(0, http.routes.pop())
        self.serve(http)
        response = self.call(api.jira_issues, VIEWER, path="/x?fixVersion=Nope")
        self.assertEqual(response.status_code, 400)
        self.assertIn("does not exist", response.data["detail"])

    @override_settings(JIRA_API_TOKEN="")
    def test_not_configured(self):
        response = self.call(api.jira_summary, VIEWER)
        self.assertEqual(response.status_code, 503)
        self.assertIn("JIRA_API_TOKEN", response.data["detail"])

    def test_timeout_setting_is_used(self):
        self.serve(jira_server(count=lambda call: {"count": 0}))
        self.call(api.jira_summary, VIEWER)
        self.assertTrue(all(c["timeout"] == 5 for c in self.http.calls))
        self.assertTrue(all(c["auth"].startswith("Basic ") for c in self.http.calls))

    def test_client_requires_configuration(self):
        with override_settings(JIRA_BASE_URL=""):
            with self.assertRaisesMessage(Exception, "JIRA_BASE_URL"):
                JiraClient()


CLOUD_ID = "11111111-2222-3333-4444-555555555555"


class JiraGatewayTests(IntegrationTestCase):
    """A token made with scopes only works through api.atlassian.com/ex/jira/<cloud id>; links stay on the site."""

    def test_cloud_id_routes_calls_through_the_gateway(self):
        self.serve(jira_server(bulk=lambda call: {"issues": [jira_issue("CT-367")]}))
        with override_settings(JIRA_CLOUD_ID=CLOUD_ID):
            JiraClient().issue_statuses(["CT-367"])
            issue = JiraClient().issue_statuses(["CT-367"])["CT-367"]
        self.assertTrue(all(c["url"].startswith(f"https://api.atlassian.com/ex/jira/{CLOUD_ID}/rest/api/3/")
                            for c in self.http.calls))
        self.assertEqual(issue["url"], "https://jira.test/browse/CT-367")

    def test_without_cloud_id_calls_go_to_the_site(self):
        self.serve(jira_server())
        JiraClient().check()
        self.assertTrue(self.http.calls[0]["url"].startswith("https://jira.test/rest/api/3/"))

    def test_invalid_cloud_id_is_reported_as_missing(self):
        with override_settings(JIRA_CLOUD_ID="not-a-cloud-id"):
            with self.assertRaisesMessage(Exception, "JIRA_CLOUD_ID"):
                JiraClient()

    def test_site_401_on_check_points_to_cloud_id(self):
        http = jira_server()
        http.routes.insert(0, ("GET", re.compile(r"/rest/api/3/myself$"), (401, {})))
        self.serve(http)
        with self.assertRaisesMessage(Exception, "JIRA_CLOUD_ID"):
            JiraClient().check()

    def test_gateway_check_without_user_scope_proves_access_with_a_visible_project(self):
        http = jira_server()
        http.routes.insert(0, ("GET", re.compile(r"/rest/api/3/myself$"), (401, {"message": "Unauthorized; scope does not match"})))
        http.on("GET", r"/rest/api/3/project/search", {"total": 42, "values": [{"key": "CS"}]})
        self.serve(http)
        with override_settings(JIRA_CLOUD_ID=CLOUD_ID):
            result = JiraClient().check()
        self.assertIsNone(result["account"])
        self.assertIn("read:jira-user", result["note"])

    def test_gateway_check_fails_when_no_project_is_visible(self):
        http = jira_server()
        http.routes.insert(0, ("GET", re.compile(r"/rest/api/3/myself$"), (401, {})))
        http.on("GET", r"/rest/api/3/project/search", {"total": 0, "values": []})
        self.serve(http)
        with override_settings(JIRA_CLOUD_ID=CLOUD_ID):
            with self.assertRaisesMessage(Exception, "can see no projects"):
                JiraClient().check()
