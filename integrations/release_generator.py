"""Release notes drafted from Bitbucket release branches and Jira.

A version is a branch named release/icrm_release_<version>_<date>, e.g. release/icrm_release_10_9_0_18122025 is
version 10.9.0 started on 18 Dec 2025 (DDMMYYYY; older branches use DDMMYY). Its changes are the commits on that
branch that aren't on the previous version's branch in the same repository (git's include/exclude): the work that
came into this version. Jira keys are taken from those commit messages, and each issue's summary, description and
type come from Jira.

The result has the same shape as an uploaded Word document (releases.api.parse_upload), so the same review screen
shows it and nothing is saved until an admin publishes it.
"""
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import date

from releases.models import Category, ReleaseVersion
from releases.services.release_categorizer import categorize

from . import bitbucket_client, cache
from .bitbucket_client import SERVICE as BITBUCKET, BitbucketClient, extract_jira_keys
from .http import BadQuery
from .jira_client import ISSUE_KEY_RE, JiraClient
from .models import BRANCH, IntegrationScope

RELEASE_PREFIX = "release/"
# icrm_release_10_9_0_18122025, optionally under release/. Copies with anything before or after (backups,
# personal copies, hotfix/...) don't match.
BRANCH_RE = re.compile(r"^(?P<prefix>release/)?icrm_release_(?P<version>\d+(?:_\d+)*)_(?P<date>\d{8}|\d{6})$")
BRANCH_PAGES = 10            # 100 matching branches per page
MAX_COMMIT_PAGES = 50        # 100 commits per page
PARALLEL_PAGES = 8
# The release tables are MySQL utf8 (3 bytes): characters outside it, such as emoji, can't be stored.
OUTSIDE_UTF8MB3 = re.compile("[\U00010000-\U0010FFFF]")
TITLE_MAX, DESCRIPTION_MAX = 500, 1000

NEW_FEATURE_TYPES = {"story", "new feature", "feature", "epic"}
BUG_TYPES = {"bug", "defect"}
SECURITY_TYPES = {"security", "vulnerability"}


def parse_branch(name: str) -> dict | None:
    """'release/icrm_release_10_9_0_18122025' -> {version: '10.9.0', date: 2025-12-18, release: True, ...}."""
    match = BRANCH_RE.match(name)
    if not match:
        return None
    parts = tuple(int(p) for p in match["version"].split("_"))
    text = match["date"]
    try:
        day, month = int(text[:2]), int(text[2:4])
        year = int(text[4:]) if len(text) == 8 else 2000 + int(text[4:])
        started = date(year, month, day)
    except ValueError:
        started = None
    return {"branch": name, "version": ".".join(map(str, parts)), "parts": parts, "date": started,
            "release": bool(match["prefix"])}


def _release_branches(client: BitbucketClient, slug: str) -> list[dict]:
    """Every icrm_release_* branch of the repository that follows the naming exactly, plain or under release/."""
    def fetch():
        names, page = [], 1
        while page <= BRANCH_PAGES:
            data = client._call(f"{client._repo(slug)}/refs/branches",
                                {"q": 'name ~ "icrm_release_"', "pagelen": 100, "page": page})
            names += [b.get("name") for b in data.get("values") or []]
            if not data.get("next"):
                break
            page += 1
        return names
    found = [parse_branch(n) for n in cache.cached(BITBUCKET, "release-branches", [slug], fetch)]
    return [b for b in found if b]


def _by_version(branches: list[dict]) -> dict[tuple, dict]:
    """One branch per version: the release/ one when both exist."""
    chosen = {}
    for b in sorted(branches, key=lambda b: b["release"]):
        chosen[b["parts"]] = b
    return chosen


def previous_branches(client: BitbucketClient, slug: str, branches) -> list[str]:
    """For the release branches among `branches`: the previous version's branch of each, except those listed too.
    Excluding them leaves only the commits of these versions (10.9.0 and 10.8.5 together: everything since 10.8.4)."""
    parsed = [b for b in map(parse_branch, branches) if b]
    if not parsed:
        return []
    by_version = _by_version(_release_branches(client, slug))
    previous = []
    for branch in parsed:
        older = [p for p in by_version if p < branch["parts"]]
        name = by_version[max(older)]["branch"] if older else None
        if name and name not in branches and name not in previous:
            previous.append(name)
    return previous


def published_branches(product, scope_branches: dict[str, list[str]]) -> list[dict]:
    """The product's published releases whose release/ branch, in one of its repositories, is in the scope:
    [{version, branches: [{repository, branch}]}]."""
    found: dict[str, list[dict]] = {}
    slugs = bitbucket_client.repositories(product)
    for slug, names in scope_branches.items():
        if slug not in slugs:
            continue
        for name in names:
            branch = parse_branch(name)
            if branch and branch["release"]:
                found.setdefault(branch["version"], []).append({"repository": slug, "branch": name})
    published = set(ReleaseVersion.objects.filter(product_id=product.id, version__in=found).values_list("version", flat=True))
    return [{"version": v, "branches": b} for v, b in found.items() if v in published]


def link_branches(product, version: str, branches: list[dict], user) -> list[str]:
    """After a drafted version is published: limit the Bitbucket, Commits & Pull Requests and Dashboard screens to its
    release branches (scope entries, as if an admin had added them). Returns "repository:branch" of those added."""
    added = []
    for entry in branches:
        slug, name = entry.get("repository"), entry.get("branch")
        branch = parse_branch(name or "")
        if slug not in bitbucket_client.repositories(product) or not branch or not branch["release"]                 or branch["version"] != version:
            continue
        _, created = IntegrationScope.objects.get_or_create(kind=BRANCH, repository=slug, value=name,
                                                            defaults={"added_by": user})
        if created:
            added.append(f"{slug}:{name}")
    if added:
        cache.invalidate()
    return added


def unlink_version(product, version: str) -> list[str]:
    """When a release is deleted, its release branches (in the product's repositories) leave the scope again."""
    slugs = bitbucket_client.repositories(product)
    rows = [r for r in IntegrationScope.objects.filter(kind=BRANCH, repository__in=slugs)
            if (b := parse_branch(r.value)) and b["release"] and b["version"] == version]
    for row in rows:
        row.delete()
    if rows:
        cache.invalidate()
    return [f"{r.repository}:{r.value}" for r in rows]


def versions(product) -> list[dict]:
    """The versions that have a release/ branch in the product's repositories, newest first, with what each one is
    compared against."""
    client = BitbucketClient()
    found: dict[tuple, dict] = {}
    for slug in bitbucket_client.repositories(product):
        by_version = _by_version(_release_branches(client, slug))
        for parts, branch in by_version.items():
            if not branch["release"]:
                continue
            older = [p for p in by_version if p < parts]
            previous = by_version[max(older)] if older else None
            entry = found.setdefault(parts, {"version": branch["version"], "date": branch["date"], "repositories": []})
            entry["repositories"].append({"repository": slug, "branch": branch["branch"],
                                          "previousBranch": previous["branch"] if previous else None,
                                          "previousVersion": previous["version"] if previous else None})
    existing = set(ReleaseVersion.objects.filter(product_id=product.id).values_list("version", flat=True))
    return [{**v, "date": v["date"].isoformat() if v["date"] else None, "published": v["version"] in existing}
            for _, v in sorted(found.items(), reverse=True)]


def _commits(client: BitbucketClient, slug: str, branch: str, previous: str | None) -> tuple[list[str], bool]:
    """Messages of the commits on `branch` that aren't on `previous` (newest first), and whether the page limit cut
    the list short. Pages are read PARALLEL_PAGES at a time, and only the message of each commit is asked for."""
    params = {"include": branch, **({"exclude": previous} if previous else {}), "pagelen": 100,
              "fields": "next,values.message"}
    path = f"{client._repo(slug)}/commits"

    def page(number):
        return client._call(path, {**params, "page": number})

    def fetch():
        messages, start = [], 1
        with ThreadPoolExecutor(max_workers=PARALLEL_PAGES) as pool:
            while start <= MAX_COMMIT_PAGES:
                numbers = range(start, min(start + PARALLEL_PAGES, MAX_COMMIT_PAGES + 1))
                for data in pool.map(page, numbers):
                    messages += [c.get("message") or "" for c in data.get("values") or []]
                    if not data.get("next"):
                        return {"messages": messages, "cut": False}
                start += PARALLEL_PAGES
        return {"messages": messages, "cut": True}
    result = cache.cached(BITBUCKET, "version-commits", [slug, params], fetch)
    return result["messages"], result["cut"]


def adf_text(node) -> str:
    """Plain text of a Jira (Atlassian Document Format) description: paragraphs and line breaks kept."""
    if not isinstance(node, dict):
        return ""
    kind = node.get("type")
    if kind == "text":
        return node.get("text") or ""
    if kind == "hardBreak":
        return "\n"
    inner = "".join(adf_text(child) for child in node.get("content") or [])
    if kind in ("paragraph", "heading", "listItem", "codeBlock", "blockquote"):
        return inner.strip() + "\n"
    return inner


def _description(raw, summary: str) -> str | None:
    text = re.sub(r"\n{2,}", "\n", OUTSIDE_UTF8MB3.sub("", adf_text(raw))).strip()
    if not text or text.strip().lower() == (summary or "").strip().lower():
        return None
    if len(text) > DESCRIPTION_MAX:
        text = text[:DESCRIPTION_MAX - 1].rsplit(" ", 1)[0] + "…"
    return text


def category_for(issue_type: str, labels, summary: str) -> str:
    kind = (issue_type or "").strip().lower()
    if kind in SECURITY_TYPES or any(label.lower() == "security" for label in labels or []):
        return Category.SECURITY
    if kind in BUG_TYPES:
        return Category.BUG_FIX
    if kind in NEW_FEATURE_TYPES:
        return Category.NEW_FEATURE
    # Tasks, sub-tasks, improvements: by their wording ("Fix ..." is a bug fix, "Add new ..." a feature).
    return categorize(summary or "")


def _jira_issues(keys: list[str]) -> dict[str, dict]:
    client = JiraClient()

    def fetch():
        found = {}
        for start in range(0, len(keys), 100):
            data = client._call("POST", "/rest/api/3/issue/bulkfetch", body={
                "issueIdsOrKeys": keys[start:start + 100],
                "fields": ["summary", "description", "issuetype", "labels", "status"],
            }) or {}
            for raw in data.get("issues") or []:
                f = raw.get("fields") or {}
                status = f.get("status") or {}
                found[raw.get("key")] = {
                    "summary": OUTSIDE_UTF8MB3.sub("", f.get("summary") or "").strip(),
                    "description": _description(f.get("description"), f.get("summary")),
                    "issueType": (f.get("issuetype") or {}).get("name"),
                    "labels": f.get("labels") or [],
                    "done": (status.get("statusCategory") or {}).get("key") == "done",
                }
        return found
    return cache.cached("Jira", "release-issues", keys, fetch)


def generate(product, version: str) -> dict:
    """A draft release of the product's `version`, in the upload preview's shape."""
    entry = next((v for v in versions(product) if v["version"] == version), None)
    if entry is None:
        raise BadQuery(f"No release/ branch for version {version} was found in the repositories of {product.label}.")
    client = BitbucketClient()
    keys, warnings, commit_count = [], [], 0
    for repo in entry["repositories"]:
        messages, cut = _commits(client, repo["repository"], repo["branch"], repo["previousBranch"])
        commit_count += len(messages)
        if cut:
            warnings.append(f"{repo['repository']}: only the newest {len(messages)} commits were read.")
        if not repo["previousBranch"]:
            warnings.append(f"{repo['repository']}: no earlier version branch to compare with, so every commit on "
                            f"{repo['branch']} was read.")
        for message in messages:
            keys += [k for k in extract_jira_keys(message) if k not in keys]
    keys = [k for k in keys if ISSUE_KEY_RE.match(k)]

    issues = _jira_issues(sorted(keys)) if keys else {}
    missing = [k for k in keys if k not in issues]
    if missing:
        warnings.append(f"{len(missing)} Jira issue(s) mentioned in commits were not found or aren't visible to the "
                        f"Jira account: {', '.join(missing[:20])}{' …' if len(missing) > 20 else ''}")
    open_keys = [k for k in keys if k in issues and not issues[k]["done"]]
    if open_keys:
        warnings.append(f"{len(open_keys)} issue(s) are not done in Jira yet: {', '.join(open_keys[:20])}"
                        f"{' …' if len(open_keys) > 20 else ''}. Remove them before publishing if they aren't in "
                        "this release.")
    if not keys:
        warnings.append("No Jira keys were found in the commit messages.")

    items = []
    for key in keys:
        issue = issues.get(key)
        if issue is None:
            continue
        items.append({"category": category_for(issue["issueType"], issue["labels"], issue["summary"]),
                      "title": (issue["summary"] or key)[:TITLE_MAX], "description": issue["description"],
                      "jiraId": key, "images": []})
    order = {c: i for i, c in enumerate(Category.values)}
    items.sort(key=lambda i: (order[i["category"]], i["jiraId"]))

    branches = ", ".join(f"{r['repository']}:{r['branch']}" for r in entry["repositories"])
    compared = ", ".join(f"{r['previousBranch']}" for r in entry["repositories"] if r["previousBranch"]) or "nothing"
    return {
        "fileName": "Bitbucket " + ", ".join(sorted({r["branch"] for r in entry["repositories"]}))[:240],
        "version": version,
        "releaseDate": entry["date"],
        "status": "RELEASED",
        "plannedLabel": None,
        "summary": "",
        "highlights": [],
        "knownIssues": [],
        "upgradeNotes": [],
        "images": [],
        "items": items,
        "warnings": [f"Read {commit_count} commits on {branches} that aren't on {compared}; "
                     f"{len(keys)} Jira issue(s) mentioned."] + warnings,
        "existingVersion": entry["published"],
        "source": {"repositories": entry["repositories"], "commits": commit_count, "jiraIssues": len(keys)},
    }
