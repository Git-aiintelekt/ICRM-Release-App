"""Bitbucket Cloud REST API 2.0: repositories, branches, commits and pull requests.

Only the repositories listed in BITBUCKET_REPOSITORIES can be read through this app. Jira keys are taken from
commit messages and PR titles for the configured Jira projects only. Their status always comes from Jira:
a commit mentioning a key says nothing about whether the issue is done.
"""
import re
import urllib.parse

from django.conf import settings

from . import cache, credentials, jira_client, scope
from .http import BadQuery, NotConfigured, NotFoundUpstream, basic_auth, request_json

SERVICE = "Bitbucket"
SLUG_RE = re.compile(r"^[A-Za-z0-9._-]{1,100}$")
BRANCH_RE = re.compile(r"^(?!.*\.\.)[A-Za-z0-9._/\-]{1,200}$")  # git forbids ".." in branch names
PR_STATES = ("OPEN", "MERGED", "DECLINED", "SUPERSEDED")
MAX_PAGE_SIZE = 50


def base_repositories() -> list[str]:
    """BITBUCKET_REPOSITORIES from .env."""
    return [slug for slug in settings.BITBUCKET_REPOSITORIES if SLUG_RE.match(slug)]


def repositories(product=None) -> list[str]:
    """The .env repositories an admin hasn't removed, then the ones added on the Bitbucket page. With a product: only
    those linked to it (releases.ProductRepository), which is what every screen shows."""
    added, hidden = scope.repository_changes()
    base = [slug for slug in base_repositories() if slug not in hidden]
    every = base + [slug for slug in added if slug not in base and SLUG_RE.match(slug)]
    if product is None:
        return every
    from releases.products import repository_slugs  # releases imports this app: imported here, not at the top
    linked = set(repository_slugs(product))
    return [slug for slug in every if slug in linked]


def _auth() -> str | None:
    if credentials.get("BITBUCKET_ACCESS_TOKEN"):
        return f"Bearer {credentials.get("BITBUCKET_ACCESS_TOKEN")}"
    if credentials.get("BITBUCKET_EMAIL") and credentials.get("BITBUCKET_API_TOKEN"):
        return basic_auth(credentials.get("BITBUCKET_EMAIL"), credentials.get("BITBUCKET_API_TOKEN"))
    return None


def is_configured() -> bool:
    return bool(credentials.get("BITBUCKET_WORKSPACE") and repositories() and _auth())


def missing_settings() -> list[str]:
    missing = []
    if not credentials.get("BITBUCKET_WORKSPACE"):
        missing.append("BITBUCKET_WORKSPACE")
    if not repositories():
        missing.append("BITBUCKET_REPOSITORIES")
    if not _auth():
        missing.append("BITBUCKET_EMAIL + BITBUCKET_API_TOKEN (or BITBUCKET_ACCESS_TOKEN)")
    return missing


def jira_key_pattern() -> re.Pattern | None:
    keys = jira_client.project_keys()
    if not keys:
        return None
    return re.compile(r"(?<![A-Za-z0-9])(" + "|".join(map(re.escape, keys)) + r")-(\d{1,7})(?![A-Za-z0-9])", re.IGNORECASE)


def extract_jira_keys(text: str) -> list[str]:
    """'CT-367 fix; also ct-12' -> ['CT-367', 'CT-12'] (configured projects only, in order, no repeats)."""
    pattern = jira_key_pattern()
    if not pattern or not text:
        return []
    seen = []
    for project, number in pattern.findall(text):
        key = f"{project.upper()}-{int(number)}"
        if key not in seen:
            seen.append(key)
    return seen


def _href(obj, name="html"):
    return ((obj or {}).get("links") or {}).get(name, {}).get("href")


def _author(commit) -> str | None:
    author = commit.get("author") or {}
    user = author.get("user") or {}
    if user.get("display_name"):
        return user["display_name"]
    raw = author.get("raw") or ""
    return raw.split("<")[0].strip() or None  # "Name <email>": keep the name only


def commit_json(raw: dict, repo: str) -> dict:
    message = raw.get("message") or ""
    return {
        "hash": raw.get("hash"),
        "shortHash": (raw.get("hash") or "")[:9],
        "author": _author(raw),
        "date": raw.get("date"),
        "message": message.strip(),
        "subject": message.strip().splitlines()[0] if message.strip() else "",
        "url": _href(raw),
        "repository": repo,
        "jiraKeys": extract_jira_keys(message),
    }


def pull_request_json(raw: dict, repo: str) -> dict:
    title = raw.get("title") or ""
    source = ((raw.get("source") or {}).get("branch") or {}).get("name")
    return {
        "id": raw.get("id"),
        "title": title,
        "state": raw.get("state"),
        "author": ((raw.get("author") or {}).get("display_name")),
        "sourceBranch": source,
        "destinationBranch": ((raw.get("destination") or {}).get("branch") or {}).get("name"),
        "createdOn": raw.get("created_on"),
        "updatedOn": raw.get("updated_on"),
        "commentCount": raw.get("comment_count"),
        "url": _href(raw),
        "repository": repo,
        "jiraKeys": extract_jira_keys(f"{title} {source or ''}"),
    }


def _page(data: dict, items) -> dict:
    return {"values": items, "page": data.get("page"), "pageLen": data.get("pagelen"), "size": data.get("size"),
            "hasNext": bool(data.get("next"))}


def _merges_out_of(message: str, branches) -> bool:
    """True for a commit that only merges one of `branches` into another branch (e.g. syncing a feature branch with
    the release branch), as written by git ("Merge branch 'x' into y") or Bitbucket ("Merged x into y",
    "Merged in x (pull request #12)")."""
    first = message.strip().splitlines()[0] if message.strip() else ""
    for b in branches:
        name = rf"(?:origin/)?{re.escape(b)}"
        if (re.match(rf"^Merge (?:remote-tracking )?branch '{name}'(?: of \S+)? into ", first)
                or re.match(rf"^Merged (?:in )?{name} (?:into |\(pull request)", first)):
            return True
    return False


def _branch(name: str) -> str:
    if not name or not BRANCH_RE.match(name):
        raise BadQuery("Invalid branch name.")
    return name


class BitbucketClient:
    def __init__(self, opener=None):
        if not is_configured():
            raise NotConfigured("Bitbucket is not configured. Missing: " + ", ".join(missing_settings()) + ".")
        self.opener = opener
        self.workspace = credentials.get("BITBUCKET_WORKSPACE")

    def _repo(self, slug: str) -> str:
        if slug not in repositories():
            raise BadQuery(f"Repository {slug!r} is not in this app's repository list.")
        return self._repo_path(slug)

    def _repo_path(self, slug: str) -> str:
        return f"/repositories/{urllib.parse.quote(self.workspace)}/{urllib.parse.quote(slug)}"

    def exists(self, slug: str) -> bool:
        """Whether the workspace has this repository (checked before an admin adds it to the list)."""
        if not SLUG_RE.match(slug):
            return False
        try:
            self._call(self._repo_path(slug))
        except NotFoundUpstream:
            return False
        return True

    def _call(self, path, params=None):
        return request_json(SERVICE, "GET", f"{settings.BITBUCKET_API_URL}{path}", auth=_auth(), params=params,
                            opener=self.opener) or {}

    @staticmethod
    def _paging(page, limit):
        return {"page": max(int(page), 1), "pagelen": min(max(int(limit), 1), MAX_PAGE_SIZE)}

    def repository(self, slug: str) -> dict:
        def fetch():
            r = self._call(self._repo(slug))
            return {
                "slug": r.get("slug") or slug,
                "name": r.get("name"),
                "fullName": r.get("full_name"),
                "workspace": self.workspace,
                "description": r.get("description"),
                "isPrivate": r.get("is_private"),
                "language": r.get("language"),
                "mainBranch": (r.get("mainbranch") or {}).get("name"),
                "createdOn": r.get("created_on"),
                "updatedOn": r.get("updated_on"),
                "size": r.get("size"),
                "url": _href(r),
            }
        return cache.cached(SERVICE, "repository", slug, fetch)

    def branches(self, slug: str, *, query=None, only=(), page=1, limit=25) -> dict:
        """`only`: limit the list to these branch names (the admin's scope for this repository)."""
        params = {**self._paging(page, limit), "sort": "-target.date"}
        clauses = []
        if only:
            clauses.append("(" + " OR ".join(f'name = "{_branch(b)}"' for b in only) + ")")
        if query:
            if not BRANCH_RE.match(query):
                raise BadQuery("Branch search may only contain letters, digits, '.', '_', '-' and '/'.")
            clauses.append(f'name ~ "{query}"')
        if clauses:
            params["q"] = " AND ".join(clauses)

        def fetch():
            data = self._call(f"{self._repo(slug)}/refs/branches", params)
            items = []
            for b in data.get("values") or []:
                target = b.get("target") or {}
                items.append({
                    "name": b.get("name"),
                    "url": _href(b),
                    "lastCommit": commit_json(target, slug) if target.get("hash") else None,
                })
            return _page(data, items)
        return cache.cached(SERVICE, "branches", [slug, params], fetch)

    def commits(self, slug: str, *, branches=(), exclude=(), page=1, limit=25) -> dict:
        """Commits on any of `branches` (newest first), or on every branch when none are given; with `exclude`, only
        those that aren't on these branches too (a release branch shows only its version's commits).

        With branches, commits that merge one of them out into another branch are left out: only work coming into
        the branch is shown. A page can then hold fewer than `limit` commits."""
        branches = [_branch(b) for b in branches]
        exclude = [_branch(b) for b in exclude] if branches else []
        params = {**self._paging(page, limit), **({"include": branches} if branches else {}),
                  **({"exclude": exclude} if exclude else {})}

        def fetch():
            try:
                data = self._call(f"{self._repo(slug)}/commits", params)
            except NotFoundUpstream:
                if branches:
                    raise BadQuery(f"Branch {', '.join(branches)} was not found in {slug}.")
                raise NotFoundUpstream(f"Repository {slug} was not found.")
            values = [c for c in data.get("values") or [] if not _merges_out_of(c.get("message") or "", branches)]
            return _page(data, [commit_json(c, slug) for c in values])
        return cache.cached(SERVICE, "commits", [slug, params], fetch)

    def pull_requests(self, slug: str, *, state=None, branches=(), page=1, limit=25) -> dict:
        """Pull requests into any of `branches` (not out of them), or all of them when none are given."""
        states = [state] if state else list(PR_STATES)
        if any(s not in PR_STATES for s in states):
            raise BadQuery("state must be one of " + ", ".join(PR_STATES) + ".")
        params = {**self._paging(page, limit), "state": states, "sort": "-updated_on"}
        if branches:
            params["q"] = " OR ".join(f'destination.branch.name = "{b}"' for b in map(_branch, branches))

        def fetch():
            data = self._call(f"{self._repo(slug)}/pullrequests", params)
            return _page(data, [pull_request_json(p, slug) for p in data.get("values") or []])
        return cache.cached(SERVICE, "pullrequests", [slug, params], fetch)

    def check(self) -> dict:
        repo = self.repository(repositories()[0])
        return {"repository": repo["fullName"]}
