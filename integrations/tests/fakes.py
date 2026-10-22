"""Test doubles: a fake HTTP server standing in for Jira/Bitbucket, and fake signed-in users.

These tests are MOCKED: they prove the request building, parsing, counting and error handling, not that the
real Jira or Bitbucket accept the credentials. No test touches the network or the database.
"""
import io
import json
import re
import urllib.error
import urllib.parse
from email.message import Message

TEST_SETTINGS = {
    "JIRA_BASE_URL": "https://jira.test",
    "JIRA_CLOUD_ID": "",
    "JIRA_EMAIL": "bot@example.test",
    "JIRA_API_TOKEN": "jira-secret-token-123",
    "JIRA_PROJECT_KEYS": ["CS", "IBP", "CT", "CP"],
    "JIRA_BUG_ISSUE_TYPES": ["Bug"],
    "JIRA_RESOLVED_STATUSES": ["Resolved"],
    "JIRA_CLOSED_STATUSES": ["Closed", "Done"],
    "JIRA_FIX_VERSION_MAP": "",
    "BITBUCKET_API_URL": "https://bb.test/2.0",
    "BITBUCKET_WORKSPACE": "acme",
    "BITBUCKET_REPOSITORIES": ["icrm-base-framework-master"],
    "BITBUCKET_EMAIL": "bot@example.test",
    "BITBUCKET_API_TOKEN": "bb-secret-token-456",
    "BITBUCKET_ACCESS_TOKEN": "",
    "INTEGRATION_CACHE_SECONDS": 300,
    "INTEGRATION_TIMEOUT_SECONDS": 5,
}
SECRETS = ("jira-secret-token-123", "bb-secret-token-456")


class _Response:
    def __init__(self, payload):
        self._raw = json.dumps(payload).encode()

    def read(self):
        return self._raw

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeHttp:
    """Route (method, path regex) -> handler(call) returning a payload, or (status, payload[, headers])."""

    def __init__(self):
        self.routes = []
        self.calls = []

    def on(self, method, path_regex, handler):
        self.routes.append((method, re.compile(path_regex + "$"), handler))
        return self

    def __call__(self, req, timeout=None):
        parsed = urllib.parse.urlsplit(req.full_url)
        call = {
            "method": req.get_method(),
            "url": req.full_url,
            "path": parsed.path,
            "query": urllib.parse.parse_qs(parsed.query),
            "body": json.loads(req.data) if req.data else None,
            "auth": req.get_header("Authorization"),
            "timeout": timeout,
        }
        self.calls.append(call)
        for method, pattern, handler in self.routes:
            if method == call["method"] and pattern.search(call["path"]):
                result = handler(call) if callable(handler) else handler
                if isinstance(result, BaseException):
                    raise result
                if isinstance(result, tuple):
                    status, payload, *rest = result
                    headers = Message()
                    for k, v in (rest[0] if rest else {}).items():
                        headers[k] = v
                    raise urllib.error.HTTPError(req.full_url, status, "error", headers, io.BytesIO(json.dumps(payload).encode()))
                return _Response(result)
        raise AssertionError(f"unexpected request {call['method']} {call['path']}")

    def bodies(self, path_part):
        return [c["body"] for c in self.calls if path_part in c["path"]]


class FakeUser:
    def __init__(self, *, admin=False, jira=False, id=7, username="tester@example.test"):
        self.id = id
        self.username = username
        self.is_admin = admin
        self.can_view_jira = admin or jira
        self.is_authenticated = True
        self.is_active = True
        self.must_change_password = False


# ---- Jira payloads ----

PROJECT_STATUSES = [
    {"name": "Bug", "statuses": [{"name": "Open"}, {"name": "In Progress"}, {"name": "Resolved"}, {"name": "Closed"}]},
    {"name": "Task", "statuses": [{"name": "Open"}, {"name": "Done"}, {"name": "Closed"}]},
]


def jira_issue(key, *, status="Open", category="new", issue_type="Task", fix_versions=(), assignee="Asha", priority="High"):
    return {
        "key": key,
        "fields": {
            "summary": f"Summary of {key}",
            "issuetype": {"name": issue_type},
            "status": {"name": status, "statusCategory": {"key": category}},
            "assignee": {"displayName": assignee} if assignee else None,
            **({"priority": {"name": priority}} if priority else {}),
            "updated": "2026-10-01T10:00:00.000+0530",
            "created": "2026-09-01T10:00:00.000+0530",
            "resolution": None,
            "fixVersions": [{"name": v} for v in fix_versions],
        },
    }


def jira_server(*, versions=None, missing_projects=(), count=None, search=None, bulk=None):
    """A Jira with projects CS/IBP/CT/CP (minus missing_projects)."""
    http = FakeHttp()

    def statuses(call):
        key = call["path"].split("/")[-2]
        if key in missing_projects:
            return 404, {"errorMessages": [f"No project could be found with key '{key}'."]}
        return PROJECT_STATUSES

    def project_versions(call):
        key = call["path"].split("/")[-2]
        return [v for v in (versions or []) if v.get("project", "CS") == key]

    http.on("GET", r"/rest/api/3/project/[A-Z]+/statuses", statuses)
    http.on("GET", r"/rest/api/3/project/[A-Z]+/versions", project_versions)
    http.on("GET", r"/rest/api/3/myself", {"displayName": "Release bot"})
    http.on("POST", r"/rest/api/3/search/approximate-count", count or (lambda call: {"count": 0}))
    http.on("POST", r"/rest/api/3/search/jql", search or (lambda call: {"issues": [], "isLast": True}))
    http.on("POST", r"/rest/api/3/issue/bulkfetch", bulk or (lambda call: {"issues": [], "issueErrors": []}))
    return http


# ---- Bitbucket payloads ----

def bb_commit(hash_, message, *, author="Sharmila K <s@example.test>", user=None, date="2026-10-06T09:00:00+00:00"):
    return {
        "hash": hash_,
        "date": date,
        "message": message,
        "author": {"raw": author, **({"user": {"display_name": user}} if user else {})},
        "links": {"html": {"href": f"https://bitbucket.test/acme/repo/commits/{hash_}"}},
    }


def bb_pull_request(id_, title, state="OPEN", source="feature/CT-1"):
    return {
        "id": id_, "title": title, "state": state, "author": {"display_name": "Dev"},
        "source": {"branch": {"name": source}}, "destination": {"branch": {"name": "dev_release"}},
        "created_on": "2026-10-01T00:00:00+00:00", "updated_on": "2026-10-02T00:00:00+00:00", "comment_count": 2,
        "links": {"html": {"href": f"https://bitbucket.test/acme/repo/pull-requests/{id_}"}},
    }
