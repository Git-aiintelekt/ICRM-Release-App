"""Jira Cloud REST API v3: issue search, status counts, fix versions, and live status of issue keys.

Jira is the source of truth for issue status. "Open" is every issue whose status category isn't Done; Done issues
are split into Resolved and Closed by status name (JIRA_RESOLVED_STATUSES / JIRA_CLOSED_STATUSES), because the
workflows use both. Configured status and issue-type names are checked against what the projects really have
before they go into JQL, since Jira rejects JQL naming a value it doesn't know.
"""
import re
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

from django.conf import settings

from . import cache, credentials, scope
from .http import AuthFailed, BadQuery, NotConfigured, NotFoundUpstream, basic_auth, request_json

SERVICE = "Jira"
PROJECT_KEY_RE = re.compile(r"^[A-Z][A-Z0-9_]{1,9}$")
ISSUE_KEY_RE = re.compile(r"^[A-Z][A-Z0-9_]{1,9}-\d{1,7}$")
CLOUD_ID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
GATEWAY_URL = "https://api.atlassian.com/ex/jira"
ISSUE_FIELDS = ["summary", "issuetype", "status", "assignee", "priority", "updated", "created", "resolution", "fixVersions"]
# Release summaries page through at most this many issues per call (100 per page).
MAX_SUMMARY_ISSUES = 5000
MAX_PAGE_SIZE = 100


def base_project_keys() -> list[str]:
    """JIRA_PROJECT_KEYS from .env: always included, changed only by editing .env."""
    return [key for key in settings.JIRA_PROJECT_KEYS if PROJECT_KEY_RE.match(key)]


def project_keys() -> list[str]:
    """The .env projects, then any an admin added on Settings → Integrations."""
    base = base_project_keys()
    return base + [key for key in scope.jira_projects() if key not in base and PROJECT_KEY_RE.match(key)]


def _cloud_id_ok() -> bool:
    return not settings.JIRA_CLOUD_ID or bool(CLOUD_ID_RE.match(settings.JIRA_CLOUD_ID))


def is_configured() -> bool:
    return bool(credentials.get("JIRA_BASE_URL") and credentials.get("JIRA_EMAIL") and credentials.get("JIRA_API_TOKEN") and project_keys()
                and _cloud_id_ok())


def missing_settings() -> list[str]:
    missing = [name for name in ("JIRA_BASE_URL", "JIRA_EMAIL", "JIRA_API_TOKEN") if not credentials.get(name)]
    if not project_keys():
        missing.append("JIRA_PROJECT_KEYS")
    if not _cloud_id_ok():
        missing.append("JIRA_CLOUD_ID (not a valid cloud ID)")
    return missing


def uses_gateway() -> bool:
    return bool(settings.JIRA_CLOUD_ID)


def api_url() -> str:
    """REST root: the Atlassian API gateway for scoped tokens, else the site itself. Browse links always use the site."""
    return f"{GATEWAY_URL}/{settings.JIRA_CLOUD_ID}" if uses_gateway() else credentials.get("JIRA_BASE_URL")


def quote(value: str) -> str:
    """A JQL string literal."""
    return '"' + str(value).replace("\\", "\\\\").replace('"', '\\"') + '"'


def jql_list(values) -> str:
    return "(" + ", ".join(quote(v) for v in values) + ")"


def browse_url(key: str) -> str:
    return f"{credentials.get("JIRA_BASE_URL")}/browse/{key}"


def parse_fix_version_map(text: str) -> dict[str, list[str]]:
    """'10.9=iCRM 10.9|10.9.1; 10.8=10.8' -> {"10.9": ["iCRM 10.9", "10.9.1"], "10.8": ["10.8"]}."""
    mapping: dict[str, list[str]] = {}
    for pair in (text or "").split(";"):
        app_version, _, jira_names = pair.partition("=")
        names = [n.strip() for n in jira_names.split("|") if n.strip()]
        if app_version.strip() and names:
            mapping[app_version.strip()] = names
    return mapping


def issue_json(raw: dict) -> dict:
    fields = raw.get("fields") or {}

    def name(field, attr="name"):
        value = fields.get(field)
        return value.get(attr) if isinstance(value, dict) else None

    status = fields.get("status") or {}
    category = (status.get("statusCategory") or {}).get("key")
    return {
        "key": raw.get("key"),
        "summary": fields.get("summary"),
        "issueType": name("issuetype"),
        "status": status.get("name"),
        "statusCategory": category,  # "new" | "indeterminate" | "done"
        "resolution": name("resolution"),
        "assignee": name("assignee", "displayName"),
        "priority": name("priority"),
        "updated": fields.get("updated"),
        "created": fields.get("created"),
        "fixVersions": [v.get("name") for v in fields.get("fixVersions") or [] if isinstance(v, dict)],
        "url": browse_url(raw.get("key") or ""),
    }


class JiraClient:
    def __init__(self, opener=None):
        if not is_configured():
            raise NotConfigured("Jira is not configured. Missing: " + ", ".join(missing_settings()) + ".")
        self.opener = opener
        self.keys = project_keys()

    def _call(self, method, path, *, params=None, body=None):
        return request_json(
            SERVICE, method, f"{api_url()}{path}",
            auth=basic_auth(credentials.get("JIRA_EMAIL"), credentials.get("JIRA_API_TOKEN")),
            params=params, body=body, opener=self.opener,
        )

    # ---- project metadata: issue types, statuses, fix versions ----

    def metadata(self) -> dict:
        return cache.cached(SERVICE, "metadata", self.keys, self._fetch_metadata)

    def _fetch_metadata(self) -> dict:
        issue_types, statuses, versions, missing = set(), set(), [], []
        for key in self.keys:
            try:
                types = self._call("GET", f"/rest/api/3/project/{key}/statuses") or []
            except NotFoundUpstream:
                missing.append(key)  # unknown project, or no permission to browse it
                continue
            for issue_type in types:
                issue_types.add(issue_type.get("name"))
                statuses.update(s.get("name") for s in issue_type.get("statuses") or [])
            for v in self._call("GET", f"/rest/api/3/project/{key}/versions") or []:
                versions.append({
                    "name": v.get("name"), "project": key, "released": bool(v.get("released")),
                    "archived": bool(v.get("archived")), "releaseDate": v.get("releaseDate"),
                    "startDate": v.get("startDate"),
                })
        visible = [k for k in self.keys if k not in missing]
        return {
            "projects": visible,
            "missingProjects": missing,
            "issueTypes": sorted(t for t in issue_types if t),
            "statuses": sorted(s for s in statuses if s),
            "fixVersions": sorted(versions, key=lambda v: (v["releaseDate"] or "9999", v["name"] or ""), reverse=True),
        }

    def _scope(self, meta) -> str:
        if not meta["projects"]:
            raise BadQuery("None of the configured Jira projects (" + ", ".join(self.keys) + ") exist or are visible to this "
                           "account. If the token was made with scopes, set JIRA_CLOUD_ID; run manage.py check_integrations.")
        return "project in (" + ", ".join(meta["projects"]) + ")"

    @staticmethod
    def _known(configured, available) -> tuple[list[str], list[str]]:
        """Split configured names into (present in Jira, missing), case-insensitively, keeping Jira's spelling."""
        by_lower = {a.lower(): a for a in available}
        found = [by_lower[c.lower()] for c in configured if c.lower() in by_lower]
        return found, [c for c in configured if c.lower() not in by_lower]

    def definitions(self, meta) -> dict:
        resolved, missing_resolved = self._known(settings.JIRA_RESOLVED_STATUSES, meta["statuses"])
        closed, missing_closed = self._known(settings.JIRA_CLOSED_STATUSES, meta["statuses"])
        bugs, missing_bugs = self._known(settings.JIRA_BUG_ISSUE_TYPES, meta["issueTypes"])
        warnings = []
        if meta["missingProjects"]:
            warnings.append("Jira projects not found or not visible: " + ", ".join(meta["missingProjects"]) + ".")
        for label, names in (("Resolved statuses", missing_resolved), ("Closed statuses", missing_closed),
                             ("Bug issue types", missing_bugs)):
            if names:
                warnings.append(f"{label} not used in these projects, ignored: " + ", ".join(names) + ".")
        return {"resolvedStatuses": resolved, "closedStatuses": closed, "bugTypes": bugs, "warnings": warnings}

    # ---- counts ----

    def count(self, jql: str) -> int:
        def fetch():
            return int((self._call("POST", "/rest/api/3/search/approximate-count", body={"jql": jql}) or {}).get("count", 0))
        return cache.cached(SERVICE, "count", jql, fetch)

    def summary(self, fix_versions=None) -> dict:
        meta = self.metadata()
        d = self.definitions(meta)
        scope = self._scope(meta)
        if fix_versions:
            scope += f" AND fixVersion in {jql_list(fix_versions)}"
        done = "statusCategory = Done"
        queries = {
            "total": scope,
            "open": f"{scope} AND statusCategory != Done",
            "done": f"{scope} AND {done}",
        }
        if d["resolvedStatuses"]:
            queries["resolved"] = f"{scope} AND {done} AND status in {jql_list(d['resolvedStatuses'])}"
        if d["closedStatuses"]:
            queries["closed"] = f"{scope} AND {done} AND status in {jql_list(d['closedStatuses'])}"
        if d["bugTypes"]:
            bug = f"{scope} AND issuetype in {jql_list(d['bugTypes'])}"
            queries.update({"bugs.total": bug, "bugs.open": f"{bug} AND statusCategory != Done", "bugs.done": f"{bug} AND {done}"})
            if d["resolvedStatuses"]:
                queries["bugs.resolved"] = f"{bug} AND {done} AND status in {jql_list(d['resolvedStatuses'])}"
            if d["closedStatuses"]:
                queries["bugs.closed"] = f"{bug} AND {done} AND status in {jql_list(d['closedStatuses'])}"

        # A few calls in parallel (not one per card): each count is cached on its own.
        with ThreadPoolExecutor(max_workers=4) as pool:
            counts = dict(zip(queries, pool.map(self.count, queries.values())))

        def group(prefix=""):
            done_n = counts.get(f"{prefix}done")
            resolved_n, closed_n = counts.get(f"{prefix}resolved"), counts.get(f"{prefix}closed")
            return {
                "total": counts.get(f"{prefix}total"),
                "open": counts.get(f"{prefix}open"),
                "done": done_n,
                "resolved": resolved_n,
                "closed": closed_n,
                # Done, but in a status that is neither a configured Resolved nor Closed status.
                "doneOther": None if done_n is None else max(0, done_n - (resolved_n or 0) - (closed_n or 0)),
            }

        return {
            "projects": meta["projects"],
            "fixVersions": list(fix_versions or []),
            "issues": group(),
            "bugs": group("bugs.") if d["bugTypes"] else None,
            "definitions": {k: d[k] for k in ("resolvedStatuses", "closedStatuses", "bugTypes")},
            "warnings": d["warnings"],
            # Jira's count endpoint is approximate for issues changed in the last few seconds.
            "approximate": True,
        }

    # ---- issue list ----

    def build_jql(self, *, text=None, issue_types=(), statuses=(), state=None, fix_versions=(), created_from=None,
                  created_to=None, keys=None) -> str:
        """created_from / created_to are dates (inclusive). keys: only these issues (a release's Jira IDs; give
        only keys Jira knows, since JQL naming an unknown key is an error); an empty list matches nothing."""
        meta = self.metadata()
        clauses = [self._scope(meta)]
        if keys is not None:
            clauses.append(f"key in {jql_list(keys)}" if keys else "key is EMPTY")
        if created_from:
            clauses.append(f'created >= "{created_from.isoformat()}"')
        if created_to:
            clauses.append(f'created < "{(created_to + timedelta(days=1)).isoformat()}"')
        if issue_types:
            clauses.append(f"issuetype in {jql_list(issue_types)}")
        if statuses:
            clauses.append(f"status in {jql_list(statuses)}")
        if fix_versions:
            clauses.append(f"fixVersion in {jql_list(fix_versions)}")
        if state:
            d = self.definitions(meta)
            if state == "open":
                clauses.append("statusCategory != Done")
            elif state == "done":
                clauses.append("statusCategory = Done")
            elif state in ("resolved", "closed"):
                names = d["resolvedStatuses"] if state == "resolved" else d["closedStatuses"]
                if not names:
                    raise BadQuery(f"No {state} statuses are configured that exist in these Jira projects.")
                clauses.append(f"statusCategory = Done AND status in {jql_list(names)}")
            elif state == "bug":
                if not d["bugTypes"]:
                    raise BadQuery("No bug issue types are configured that exist in these Jira projects.")
                clauses.append(f"issuetype in {jql_list(d['bugTypes'])}")
        if text:
            text = text.strip()
            if ISSUE_KEY_RE.match(text.upper()):
                clauses.append(f"key = {quote(text.upper())}")
            else:
                # Characters with a meaning in Jira's text search are dropped, so any input is a plain search.
                words = re.sub(r'[+\-&|!(){}\[\]^~*?\\:"/]', " ", text).split()
                if words:
                    clauses.append(f"text ~ {quote(' '.join(words))}")
        return " AND ".join(clauses) + " ORDER BY updated DESC"

    def search(self, jql: str, *, page_token=None, limit=25) -> dict:
        body = {"jql": jql, "maxResults": min(max(int(limit), 1), MAX_PAGE_SIZE), "fields": ISSUE_FIELDS}
        if page_token:
            body["nextPageToken"] = page_token

        def fetch():
            data = self._call("POST", "/rest/api/3/search/jql", body=body) or {}
            return {
                "issues": [issue_json(raw) for raw in data.get("issues") or []],
                "nextPageToken": data.get("nextPageToken"),
                "isLast": bool(data.get("isLast", not data.get("nextPageToken"))),
            }

        page = cache.cached(SERVICE, "search", body, fetch)
        count_jql = jql.split(" ORDER BY ")[0]
        return {**page, "total": self.count(count_jql), "totalApproximate": True}

    # ---- live status of issue keys (used for Bitbucket commits) ----

    def issue_statuses(self, keys) -> dict[str, dict]:
        """{key: issue} for the keys Jira knows and this account can see; unknown keys are simply absent."""
        keys = sorted({k.upper() for k in keys if ISSUE_KEY_RE.match(k.upper())})
        if not keys:
            return {}

        def fetch():
            found = {}
            for start in range(0, len(keys), 100):
                data = self._call("POST", "/rest/api/3/issue/bulkfetch", body={
                    "issueIdsOrKeys": keys[start:start + 100], "fields": ["summary", "status", "issuetype", "resolution"],
                }) or {}
                for raw in data.get("issues") or []:
                    issue = issue_json(raw)
                    found[issue["key"]] = issue
            return found

        return cache.cached(SERVICE, "statuses", keys, fetch)

    # ---- release-wise summaries ----

    def release_summaries(self, app_versions, only=()) -> dict:
        """Per fix version: total, open, done, resolved, closed, bugs, open bugs (exact counts).

        With JIRA_FIX_VERSION_MAP, rows are the app's release versions and the Jira fix versions mapped to them.
        Without it, rows are the most recent Jira fix versions exactly as Jira names them, and `candidates` lists
        Jira fix versions whose name contains an app version: unconfirmed hints to help write the map.
        `only` (the fix versions an admin limited the screens to) overrides both: one row per listed fix version.
        """
        meta = self.metadata()
        d = self.definitions(meta)
        jira_names = {v["name"] for v in meta["fixVersions"]}
        mapping = parse_fix_version_map(settings.JIRA_FIX_VERSION_MAP)
        warnings = list(d["warnings"])

        if only:
            by_name = {v["name"]: v for v in meta["fixVersions"]}
            rows = []
            for name in only:
                v = by_name.get(name)
                if v is None:
                    warnings.append(f"Fix version {name} is no longer in Jira.")
                    continue
                rows.append({"label": name, "appVersion": None, "fixVersions": [name], "project": v["project"],
                             "released": v["released"], "releaseDate": v["releaseDate"]})
            mapping = {}
        elif mapping:
            rows = []
            for app_version, names in mapping.items():
                present = [n for n in names if n in jira_names]
                if len(present) < len(names):
                    warnings.append(f"Mapped fix versions not found in Jira for {app_version}: "
                                    + ", ".join(n for n in names if n not in jira_names) + ".")
                rows.append({"label": app_version, "appVersion": app_version, "fixVersions": present})
        else:
            recent = [v for v in meta["fixVersions"] if not v["archived"]][:12]
            rows = [{"label": v["name"], "appVersion": None, "fixVersions": [v["name"]], "project": v["project"],
                     "released": v["released"], "releaseDate": v["releaseDate"]} for v in recent]

        wanted = sorted({n for row in rows for n in row["fixVersions"]})
        tallies, truncated = self._tally_fix_versions(meta, d, wanted) if wanted else ({}, False)
        if truncated:
            warnings.append(f"More than {MAX_SUMMARY_ISSUES} issues in these fix versions; counts cover the first {MAX_SUMMARY_ISSUES}.")
        for row in rows:
            total = Counter()
            for name in row["fixVersions"]:
                total.update(tallies.get(name, {}))
            row["counts"] = {k: total.get(k, 0) for k in ("total", "open", "done", "resolved", "closed", "bugs", "openBugs")}

        candidates = {}
        if not mapping and not only:
            for app_version in app_versions:
                pattern = re.compile(rf"(?<![\d.]){re.escape(app_version)}(?![\d])")
                hits = sorted(n for n in jira_names if n and pattern.search(n))
                if hits:
                    candidates[app_version] = hits
        return {"mapped": bool(mapping), "rows": rows, "candidates": candidates, "warnings": warnings,
                "definitions": {k: d[k] for k in ("resolvedStatuses", "closedStatuses", "bugTypes")}}

    def _tally_fix_versions(self, meta, d, names):
        def fetch():
            jql = f"{self._scope(meta)} AND fixVersion in {jql_list(names)}"
            tallies = defaultdict(Counter)
            resolved = {s.lower() for s in d["resolvedStatuses"]}
            closed = {s.lower() for s in d["closedStatuses"]}
            bugs = {t.lower() for t in d["bugTypes"]}
            wanted = set(names)
            token, seen = None, 0
            while True:
                body = {"jql": jql, "maxResults": MAX_PAGE_SIZE, "fields": ["status", "issuetype", "fixVersions"]}
                if token:
                    body["nextPageToken"] = token
                data = self._call("POST", "/rest/api/3/search/jql", body=body) or {}
                for raw in data.get("issues") or []:
                    issue = issue_json(raw)
                    is_done = issue["statusCategory"] == "done"
                    status = (issue["status"] or "").lower()
                    is_bug = (issue["issueType"] or "").lower() in bugs
                    for name in set(issue["fixVersions"]) & wanted:
                        t = tallies[name]
                        t["total"] += 1
                        t["done" if is_done else "open"] += 1
                        t["resolved"] += int(is_done and status in resolved)
                        t["closed"] += int(is_done and status in closed)
                        t["bugs"] += int(is_bug)
                        t["openBugs"] += int(is_bug and not is_done)
                    seen += 1
                token = data.get("nextPageToken")
                if not token or data.get("isLast"):
                    return {k: dict(v) for k, v in tallies.items()}, False
                if seen >= MAX_SUMMARY_ISSUES:
                    return {k: dict(v) for k, v in tallies.items()}, True

        return cache.cached(SERVICE, "tally", names, fetch)

    def check(self) -> dict:
        """A cheap call proving the credentials work.

        On the site URL a token Jira doesn't accept is treated as anonymous: searches come back empty instead of
        failing, so /myself (401 for anonymous) is the proof. Through the gateway every call is authenticated, and
        /myself needs the read:jira-user scope, so without it a visible project is the proof instead.
        """
        try:
            me = self._call("GET", "/rest/api/3/myself") or {}
        except AuthFailed as exc:
            if exc.upstream_status != 401:
                raise
            if not uses_gateway():
                raise AuthFailed(f"{exc} A token made with \"Create API token with scopes\" also needs JIRA_CLOUD_ID.",
                                 upstream_status=401)
            visible = self._call("GET", "/rest/api/3/project/search", params={"maxResults": 1}) or {}
            if not visible.get("total"):
                raise AuthFailed("Jira accepted the token but it can see no projects. Check its scopes "
                                 "(read:jira-work) and the account's project permissions.", upstream_status=401)
            cache.mark_ok(SERVICE)
            return {"account": None, "note": "Account name unavailable: the token lacks the read:jira-user scope."}
        cache.mark_ok(SERVICE)
        return {"account": me.get("displayName")}
