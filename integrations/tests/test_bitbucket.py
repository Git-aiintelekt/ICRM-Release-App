"""Bitbucket (MOCKED responses): repositories, branches, commits, PRs, Jira key linking, failures."""
from django.test import override_settings

from integrations import api
from integrations.bitbucket_client import extract_jira_keys

from .base import IntegrationTestCase
from .fakes import SECRETS, FakeHttp, FakeUser, bb_commit, bb_pull_request, jira_issue, jira_server

VIEWER = FakeUser(jira=True)
REPO = "/repositories/acme/icrm-base-framework-master"


def bitbucket_and_jira(*, commits=None, prs=None, bulk=None):
    http = jira_server(bulk=bulk or (lambda call: {"issues": [
        jira_issue("CT-367", status="In Progress", category="indeterminate"),
        jira_issue("CS-10", status="Closed", category="done"),
    ], "issueErrors": [{"errorMessages": ["CP-999 not found"]}]}))
    http.on("GET", REPO, {
        "slug": "icrm-base-framework-master", "name": "icrm-base-framework-master",
        "full_name": "acme/icrm-base-framework-master", "is_private": True, "language": "java",
        "mainbranch": {"name": "master"}, "updated_on": "2026-10-06T00:00:00+00:00",
        "links": {"html": {"href": "https://bitbucket.test/acme/icrm-base-framework-master"}},
    })
    http.on("GET", REPO + "/refs/branches", {"values": [
        {"name": "icrm_release_10_9_0", "target": bb_commit("a" * 40, "CS-10 release"), "links": {"html": {"href": "https://b/br"}}},
    ], "page": 1, "pagelen": 25, "size": 354, "next": "https://bb.test/next"})
    http.on("GET", REPO + r"/commits(/.+)?", commits or {"values": [
        bb_commit("7dc267dbd" + "0" * 31, "CT-367 Conflict Resolve\n\nmore text", user="Sharmila K"),
        bb_commit("1" * 40, "Merged in dev (pull request #4650)\n\nCP-999 UTF-8 ABC-12"),
    ], "page": 1, "pagelen": 25, "next": "https://bb.test/next"})
    http.on("GET", REPO + "/pullrequests", prs or {"values": [
        bb_pull_request(4650, "CT-367 survey API", "MERGED"),
        bb_pull_request(4651, "No ticket here", "OPEN", source="hotfix"),
    ], "page": 1, "pagelen": 25, "size": 2})
    return http


class BitbucketTests(IntegrationTestCase):
    def test_extract_jira_keys_only_for_configured_projects(self):
        self.assertEqual(extract_jira_keys("CT-367 fix; ct-12, CS-0010 and CT-367 again"), ["CT-367", "CT-12", "CS-10"])
        self.assertEqual(extract_jira_keys("UTF-8 ABC-12 XCS-1 CS-1A"), [])

    def test_repositories(self):
        self.serve(bitbucket_and_jira())
        body = self.call(api.bitbucket_repositories, VIEWER).data
        repo = body["repositories"][0]
        self.assertEqual(body["workspace"], "acme")
        self.assertEqual(repo["fullName"], "acme/icrm-base-framework-master")
        self.assertEqual(repo["mainBranch"], "master")
        self.assertEqual(repo["url"], "https://bitbucket.test/acme/icrm-base-framework-master")

    @override_settings(BITBUCKET_REPOSITORIES=["icrm-base-framework-master", "sql_group"])
    def test_only_the_products_repositories_and_their_branches_are_listed(self):
        self.serve(bitbucket_and_jira())
        self.product_repositories = ["icrm-base-framework-master"]  # sql_group belongs to another product
        self.scope["branches"] = {"icrm-base-framework-master": ["release/a"], "sql_group": ["main", "dev"]}
        body = self.call(api.bitbucket_repositories, VIEWER).data
        self.assertEqual([r["slug"] for r in body["repositories"]], ["icrm-base-framework-master"])
        self.assertEqual(body["branches"], {"icrm-base-framework-master": ["release/a"]})

    @override_settings(BITBUCKET_REPOSITORIES=["icrm-base-framework-master", "sql_group"])
    def test_second_repository_is_configuration_only(self):
        http = self.serve(bitbucket_and_jira())
        http.on("GET", "/repositories/acme/sql_group", (404, {"error": {"message": "Repository not found"}}))
        http.routes.insert(0, http.routes.pop())
        repos = self.call(api.bitbucket_repositories, VIEWER).data["repositories"]
        self.assertEqual([r["slug"] for r in repos], ["icrm-base-framework-master", "sql_group"])
        self.assertIn("not found", repos[1]["error"])  # one failing repository doesn't hide the other

    def test_branches(self):
        self.serve(bitbucket_and_jira())
        body = self.call(api.bitbucket_branches, VIEWER, path="/x?q=icrm_release&page=2", slug="icrm-base-framework-master").data
        self.assertEqual(body["values"][0]["name"], "icrm_release_10_9_0")
        self.assertEqual(body["values"][0]["lastCommit"]["jiraKeys"], ["CS-10"])
        self.assertTrue(body["hasNext"])
        query = self.http.calls[-1]["query"]
        self.assertEqual(query["q"], ['name ~ "icrm_release"'])
        self.assertEqual(query["page"], ["2"])

    def test_commits_with_live_jira_status(self):
        self.serve(bitbucket_and_jira())
        body = self.call(api.bitbucket_commits, VIEWER, path="/x?branch=icrm_release_10_9_0", slug="icrm-base-framework-master").data
        first, second = body["values"]
        self.assertEqual(first["shortHash"], "7dc267dbd")
        self.assertEqual(first["author"], "Sharmila K")
        self.assertEqual(first["subject"], "CT-367 Conflict Resolve")
        self.assertEqual(first["date"], "2026-10-06T09:00:00+00:00")
        self.assertTrue(first["url"].endswith("/commits/7dc267dbd" + "0" * 31))
        # A commit exists, but the issue is still In Progress in Jira: shown as such, never as closed.
        self.assertEqual(first["jiraIssues"][0]["status"], "In Progress")
        self.assertEqual(first["jiraIssues"][0]["statusCategory"], "indeterminate")
        self.assertEqual(second["author"], "Sharmila K")  # from "Name <email>", email not exposed
        self.assertNotIn("s@example.test", str(body))
        self.assertEqual(second["jiraKeys"], ["CP-999"])
        self.assertEqual(second["jiraIssues"][0]["status"], None)
        self.assertTrue(second["jiraIssues"][0]["notFound"])
        self.assertIsNone(body["jiraWarning"])
        self.assertTrue(self.http.calls[0]["path"].endswith("/commits"))
        self.assertEqual(self.http.calls[0]["query"]["include"], ["icrm_release_10_9_0"])
        bulk = self.http.bodies("bulkfetch")
        self.assertEqual(bulk, [{"issueIdsOrKeys": ["CP-999", "CT-367"], "fields": ["summary", "status", "issuetype", "resolution"]}])

    @override_settings(JIRA_API_TOKEN="")
    def test_commits_without_jira_report_unknown_status(self):
        self.serve(bitbucket_and_jira())
        body = self.call(api.bitbucket_commits, VIEWER, slug="icrm-base-framework-master").data
        self.assertIn("not configured", body["jiraWarning"])
        link = body["values"][0]["jiraIssues"][0]
        self.assertIsNone(link["status"])
        self.assertFalse(link["notFound"])  # unknown, not "doesn't exist"

    def test_commits_when_jira_fails_still_list_commits(self):
        self.serve(bitbucket_and_jira(bulk=(401, {})))
        response = self.call(api.bitbucket_commits, VIEWER, slug="icrm-base-framework-master")
        self.assertEqual(response.status_code, 200)
        self.assertIn("unavailable", response.data["jiraWarning"])
        self.assertEqual(len(response.data["values"]), 2)

    def test_pull_requests(self):
        self.serve(bitbucket_and_jira())
        body = self.call(api.bitbucket_pull_requests, VIEWER, slug="icrm-base-framework-master").data
        merged, open_ = body["values"]
        self.assertEqual((merged["id"], merged["state"], merged["jiraKeys"]), (4650, "MERGED", ["CT-367", "CT-1"]))
        self.assertEqual(merged["sourceBranch"], "feature/CT-1")
        self.assertEqual(merged["url"], "https://bitbucket.test/acme/repo/pull-requests/4650")
        self.assertEqual(open_["jiraIssues"], [])
        # Every state is requested, since Bitbucket only returns OPEN by default.
        self.assertEqual(self.http.calls[0]["query"]["state"], ["OPEN", "MERGED", "DECLINED", "SUPERSEDED"])

    def test_pull_request_state_filter(self):
        self.serve(bitbucket_and_jira())
        self.call(api.bitbucket_pull_requests, VIEWER, path="/x?state=merged", slug="icrm-base-framework-master")
        self.assertEqual(self.http.calls[0]["query"]["state"], ["MERGED"])
        response = self.call(api.bitbucket_pull_requests, VIEWER, path="/x?state=bogus", slug="icrm-base-framework-master")
        self.assertEqual(response.status_code, 400)

    def test_only_configured_repositories_can_be_read(self):
        self.serve(FakeHttp())  # no request may be sent
        response = self.call(api.bitbucket_commits, VIEWER, slug="other-repo")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.http.calls, [])

    def test_invalid_branch_names_are_rejected(self):
        self.serve(FakeHttp())
        for branch in ("a b", 'x"y', "../../etc"):
            response = self.call(api.bitbucket_commits, VIEWER, path=f"/x?branch={branch}", slug="icrm-base-framework-master")
            self.assertIn(response.status_code, (400,), branch)
        response = self.call(api.bitbucket_branches, VIEWER, path='/x?q=a"b', slug="icrm-base-framework-master")
        self.assertEqual(response.status_code, 400)

    def test_missing_branch_is_400(self):
        self.serve(bitbucket_and_jira(commits=(404, {"error": {"message": "Commit not found"}})))
        response = self.call(api.bitbucket_commits, VIEWER, path="/x?branch=nope", slug="icrm-base-framework-master")
        self.assertEqual(response.status_code, 400)
        self.assertIn("nope", response.data["detail"])

    def test_bad_credentials_never_echo_the_token(self):
        self.serve(bitbucket_and_jira(commits=(401, {"error": {"message": "Unauthorized"}})))
        response = self.call(api.bitbucket_commits, VIEWER, slug="icrm-base-framework-master")
        self.assertEqual(response.status_code, 502)
        self.assertIn("rejected the credentials", response.data["detail"])
        for secret in SECRETS:
            self.assertNotIn(secret, str(response.data))

    def test_rate_limited(self):
        self.serve(bitbucket_and_jira(commits=(429, {}, {"Retry-After": "3600"})))
        self.assertEqual(self.call(api.bitbucket_commits, VIEWER, slug="icrm-base-framework-master").status_code, 503)

    def test_auth_header_basic_or_bearer(self):
        self.serve(bitbucket_and_jira())
        self.call(api.bitbucket_repositories, VIEWER)
        self.assertTrue(self.http.calls[-1]["auth"].startswith("Basic "))
        from django.core.cache import cache
        cache.clear()
        with override_settings(BITBUCKET_ACCESS_TOKEN="repo-token", BITBUCKET_API_TOKEN=""):
            self.call(api.bitbucket_repositories, VIEWER)
        self.assertEqual(self.http.calls[-1]["auth"], "Bearer repo-token")

    @override_settings(BITBUCKET_WORKSPACE="")
    def test_not_configured(self):
        response = self.call(api.bitbucket_repositories, VIEWER)
        self.assertEqual(response.status_code, 503)
        self.assertIn("BITBUCKET_WORKSPACE", response.data["detail"])


class ScopeTests(IntegrationTestCase):
    """An admin's chosen branches limit the branch list, commits and pull requests of that repository."""

    SLUG = "icrm-base-framework-master"

    def setUp(self):
        super().setUp()
        self.scope["branches"] = {self.SLUG: ["icrm_release_10_9_0", "icrm_release_11_0"]}
        self.serve(bitbucket_and_jira())

    def test_branch_list_is_limited_to_the_scope(self):
        body = self.call(api.bitbucket_branches, VIEWER, path="/x?q=release", slug=self.SLUG).data
        self.assertEqual(body["scopeBranches"], ["icrm_release_10_9_0", "icrm_release_11_0"])
        self.assertEqual(self.http.calls[-1]["query"]["q"],
                         ['(name = "icrm_release_10_9_0" OR name = "icrm_release_11_0") AND name ~ "release"'])

    def test_commits_default_to_every_scoped_branch(self):
        self.assertEqual(self.call(api.bitbucket_commits, VIEWER, slug=self.SLUG).status_code, 200)
        self.assertEqual(self.http.calls[0]["query"]["include"], ["icrm_release_10_9_0", "icrm_release_11_0"])

    def test_commits_of_one_scoped_branch(self):
        self.call(api.bitbucket_commits, VIEWER, path="/x?branch=icrm_release_11_0", slug=self.SLUG)
        self.assertEqual(self.http.calls[0]["query"]["include"], ["icrm_release_11_0"])

    def test_a_branch_outside_the_scope_is_refused(self):
        for view in (api.bitbucket_commits, api.bitbucket_pull_requests):
            response = self.call(view, VIEWER, path="/x?branch=master", slug=self.SLUG)
            self.assertEqual(response.status_code, 400)
            self.assertIn("Only these branches", str(response.data))
        self.assertEqual(self.http.calls, [])

    def test_pull_requests_only_into_scoped_branches(self):
        self.call(api.bitbucket_pull_requests, VIEWER, path="/x?branch=icrm_release_11_0", slug=self.SLUG)
        query = self.http.calls[0]["query"]
        self.assertEqual(query["q"], ['destination.branch.name = "icrm_release_11_0"'])

    def test_merges_out_of_a_branch_are_recognised(self):
        from integrations.bitbucket_client import _merges_out_of
        out = ["Merge branch 'dev_release_18072023' into feature/CT-1",
               "Merge remote-tracking branch 'origin/dev_release_18072023' into CT-9",
               "Merge branch 'dev_release_18072023' of https://bitbucket.org/acme/repo into CT-9",
               "Merged dev_release_18072023 into feature/CT-1",
               "Merged in dev_release_18072023 (pull request #812)"]
        into = ["Merged in feature/CT-1 (pull request #813)", "Merge branch 'CT-9' into dev_release_18072023",
                "CT-1: fix login loop", ""]
        self.assertTrue(all(_merges_out_of(m, ["dev_release_18072023"]) for m in out))
        self.assertFalse(any(_merges_out_of(m, ["dev_release_18072023"]) for m in into))

    def test_other_repositories_are_not_limited(self):
        self.scope["branches"] = {"sql_group": ["main"]}
        self.call(api.bitbucket_commits, VIEWER, slug=self.SLUG)
        self.assertNotIn("include", self.http.calls[0]["query"])
