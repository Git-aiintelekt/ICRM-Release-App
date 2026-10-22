"""Release notes drafted from release/ branches: branch naming, version pairing, Jira text and categories (MOCKED)."""
from datetime import date
from unittest import mock

from integrations import release_generator as g

from .base import IntegrationTestCase
from .fakes import FakeHttp, FakeUser

ADMIN = FakeUser(admin=True)
VIEWER = FakeUser(jira=True)

BRANCHES = {
    "icrm-b2b-master": ["release/icrm_release_10_9_0_18122025", "icrm_release_10_9_0_18122025",
                        "icrm_release_10_9_0_18122025_bkp", "citi_icrm_release_10_9_0_18122025_jan826",
                        "icrm_release_10_8_5_08102025", "hotfix/pb_icrm_release_10_7_27022025",
                        "icrm_release_10_3_4_281024"],
    "icrm-base-framework-master": ["icrm_release_10_9_0_18122025"],
}


class BranchNameTests(IntegrationTestCase):
    def test_version_and_date_come_from_the_name(self):
        b = g.parse_branch("release/icrm_release_10_9_0_18122025")
        self.assertEqual((b["version"], b["date"], b["release"]), ("10.9.0", date(2025, 12, 18), True))
        self.assertEqual(g.parse_branch("icrm_release_10_3_4_281024")["date"], date(2024, 10, 28))
        self.assertEqual(g.parse_branch("icrm_release_10_7_3_2_04072025")["version"], "10.7.3.2")
        self.assertEqual(g.parse_branch("icrm_release_10_8_01082025")["version"], "10.8")
        self.assertIsNone(g.parse_branch("icrm_release_10_9_0_99999999")["date"])

    def test_copies_and_other_branches_are_not_versions(self):
        for name in ("icrm_release_10_9_0_18122025_bkp", "citi_icrm_release_10_9_0_18122025_jan826",
                     "hotfix/pb_icrm_release_10_7_27022025", "dev_release_18072023", "release/other"):
            self.assertIsNone(g.parse_branch(name), name)


class CategoryAndTextTests(IntegrationTestCase):
    def test_category_from_issue_type_then_wording(self):
        self.assertEqual(g.category_for("Bug", [], "Anything"), "BUG_FIX")
        self.assertEqual(g.category_for("Story", [], "Anything"), "NEW_FEATURE")
        self.assertEqual(g.category_for("Task", ["Security"], "Anything"), "SECURITY")
        self.assertEqual(g.category_for("Task", [], "Fix the export"), "BUG_FIX")
        self.assertEqual(g.category_for("Task", [], "Tidy the layout"), "IMPROVEMENT")

    def test_description_is_plain_text_and_skips_a_repeat_of_the_summary(self):
        adf = {"type": "doc", "content": [
            {"type": "paragraph", "content": [{"type": "text", "text": "Line one"}, {"type": "hardBreak"},
                                              {"type": "text", "text": "line two"}]},
            {"type": "paragraph", "content": [{"type": "text", "text": "Second paragraph"}]}]}
        self.assertEqual(g._description(adf, "Summary"), "Line one\nline two\nSecond paragraph")
        same = {"type": "doc", "content": [{"type": "paragraph", "content": [{"type": "text", "text": "Summary"}]}]}
        self.assertIsNone(g._description(same, "Summary"))
        self.assertIsNone(g._description(None, "Summary"))

    def test_characters_mysql_utf8_cannot_store_are_dropped(self):
        adf = {"type": "doc", "content": [{"type": "paragraph", "content": [{"type": "text", "text": "Done \U0001F600 ✓"}]}]}
        self.assertEqual(g._description(adf, "Summary"), "Done  ✓")


class VersionsTests(IntegrationTestCase):
    def setUp(self):
        super().setUp()
        self.serve(FakeHttp())
        self.repository_changes = (["icrm-b2b-master"], [])
        mock.patch("integrations.release_generator._release_branches",
                   side_effect=lambda client, slug: [b for b in map(g.parse_branch, BRANCHES.get(slug, [])) if b]).start()
        mock.patch("integrations.release_generator.ReleaseVersion.objects.values_list", return_value=["10.9.0"]).start()

    def test_only_release_branches_are_versions_compared_with_the_previous_version(self):
        found = g.versions()
        self.assertEqual([v["version"] for v in found], ["10.9.0"])
        self.assertTrue(found[0]["published"])
        self.assertEqual(found[0]["repositories"], [{
            "repository": "icrm-b2b-master", "branch": "release/icrm_release_10_9_0_18122025",
            "previousBranch": "icrm_release_10_8_5_08102025", "previousVersion": "10.8.5"}])

    def test_draft_lists_jira_issues_from_the_version_commits(self):
        commits = mock.patch("integrations.release_generator._commits", return_value=(
            ["CS-2 fix export", "Merged in feature/CS-1 (pull request #4)", "no key here", "CS-2 again", "CS-9 gone"],
            False)).start()
        mock.patch("integrations.release_generator._jira_issues", return_value={
            "CS-1": {"summary": "New report", "description": "Details", "issueType": "Story", "labels": [], "done": True},
            "CS-2": {"summary": "Export fails", "description": None, "issueType": "Bug", "labels": [], "done": False},
        }).start()
        draft = g.generate("10.9.0")
        commits.assert_called_once_with(mock.ANY, "icrm-b2b-master", "release/icrm_release_10_9_0_18122025",
                                        "icrm_release_10_8_5_08102025")
        self.assertEqual([(i["category"], i["jiraId"], i["title"]) for i in draft["items"]],
                         [("NEW_FEATURE", "CS-1", "New report"), ("BUG_FIX", "CS-2", "Export fails")])
        self.assertEqual((draft["version"], draft["releaseDate"], draft["existingVersion"]), ("10.9.0", "2025-12-18", True))
        warnings = " ".join(draft["warnings"])
        self.assertIn("CS-9", warnings)       # not found in Jira
        self.assertIn("not done", warnings)   # CS-2 is still open

    def test_unknown_version_and_access(self):
        from integrations import api
        self.assertEqual(self.call(api.release_draft, ADMIN, method="post", data={"version": "9.9"}).status_code, 400)
        self.assertEqual(self.call(api.release_draft, ADMIN, method="post", data={"version": "x;y"}).status_code, 400)
        self.assertEqual(self.call(api.release_versions, VIEWER).status_code, 403)
        self.assertEqual(self.call(api.release_draft, VIEWER, method="post", data={"version": "10.9.0"}).status_code, 403)


class PublishedBranchTests(IntegrationTestCase):
    """After publishing: the release branches limit the screens, commits are the version's own, the dashboard counts."""

    def setUp(self):
        super().setUp()
        self.serve(FakeHttp())
        self.repository_changes = (["icrm-b2b-master"], [])
        mock.patch("integrations.release_generator._release_branches",
                   side_effect=lambda client, slug: [b for b in map(g.parse_branch, BRANCHES.get(slug, [])) if b]).start()

    def test_previous_version_branch_is_excluded_unless_also_shown(self):
        client = mock.Mock()
        self.assertEqual(g.previous_branches(client, "icrm-b2b-master", ["release/icrm_release_10_9_0_18122025"]),
                         ["icrm_release_10_8_5_08102025"])
        both = ["release/icrm_release_10_9_0_18122025", "icrm_release_10_8_5_08102025"]
        self.assertEqual(g.previous_branches(client, "icrm-b2b-master", both), ["icrm_release_10_3_4_281024"])
        self.assertEqual(g.previous_branches(client, "icrm-b2b-master", ["dev_release_18072023"]), [])

    def test_link_adds_only_this_versions_release_branches(self):
        objects = mock.patch("integrations.release_generator.IntegrationScope.objects").start()
        objects.get_or_create.return_value = (mock.Mock(), True)
        added = g.link_branches("10.9.0", [
            {"repository": "icrm-b2b-master", "branch": "release/icrm_release_10_9_0_18122025"},
            {"repository": "icrm-b2b-master", "branch": "release/icrm_release_10_8_5_08102025"},  # another version
            {"repository": "icrm-b2b-master", "branch": "icrm_release_10_9_0_18122025"},          # not under release/
            {"repository": "unknown-repo", "branch": "release/icrm_release_10_9_0_18122025"},
        ], ADMIN)
        self.assertEqual(added, ["icrm-b2b-master:release/icrm_release_10_9_0_18122025"])
        objects.get_or_create.assert_called_once()

    def test_dashboard_counts_the_published_releases_jira_issues(self):
        from integrations import api
        self.scope["branches"] = {"icrm-b2b-master": ["release/icrm_release_10_9_0_18122025", "feature/x"]}
        mock.patch("integrations.release_generator.ReleaseVersion.objects.filter").start() \
            .return_value.values_list.return_value = ["10.9.0"]
        items = mock.patch("integrations.api.ReleaseItem.objects.filter").start()
        items.return_value.exclude.return_value.exclude.return_value.values_list.return_value = ["CS-1", "CS-2", "cs-3"]
        client = mock.Mock()
        client.issue_statuses.return_value = {
            "CS-1": {"statusCategory": "done", "issueType": "Bug"},
            "CS-2": {"statusCategory": "indeterminate", "issueType": "Bug"},
        }
        rows = api._release_branch_counts(client, self.scope)
        self.assertEqual(rows, [{"version": "10.9.0",
                                 "branches": [{"repository": "icrm-b2b-master",
                                               "branch": "release/icrm_release_10_9_0_18122025"}],
                                 "counts": {"total": 3, "done": 1, "open": 1, "notFound": 1, "bugs": 2, "openBugs": 1}}])
