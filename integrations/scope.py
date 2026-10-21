"""The branches and Jira fix versions admins limited the screens to, and the Jira projects they added
(see models.IntegrationScope)."""
from django.core.cache import cache

from .models import BRANCH, FIX_VERSION, JIRA_PROJECT, REPOSITORY, REPOSITORY_HIDDEN, VERSION_START, IntegrationScope

_EXTRAS_KEY = "integrations:scope-extras"
_EXTRA_KINDS = (JIRA_PROJECT, REPOSITORY, REPOSITORY_HIDDEN)


def _extras() -> dict:
    """Projects and repositories admins added or removed. Read on every Jira key lookup and repository list, so
    cached until the next add / remove."""
    extras = cache.get(_EXTRAS_KEY)
    if extras is None:
        extras = {kind: [] for kind in _EXTRA_KINDS}
        for kind, value in IntegrationScope.objects.filter(kind__in=_EXTRA_KINDS).values_list("kind", "value"):
            extras[kind].append(value)
        cache.set(_EXTRAS_KEY, extras, timeout=None)
    return extras


def jira_projects() -> list[str]:
    return _extras()[JIRA_PROJECT]


def repository_changes() -> tuple[list[str], list[str]]:
    """(added repository slugs, removed .env slugs)."""
    extras = _extras()
    return extras[REPOSITORY], extras[REPOSITORY_HIDDEN]


def forget() -> None:
    cache.delete(_EXTRAS_KEY)


def current() -> dict:
    """{"branches": {slug: [names]}, "fixVersions": [names], "entries": [...]}: one query, read once per request."""
    branches: dict[str, list[str]] = {}
    fix_versions: list[str] = []
    projects: list[str] = []
    version_starts: dict[str, str] = {}
    entries = []
    for row in IntegrationScope.objects.all():
        if row.kind == BRANCH:
            branches.setdefault(row.repository, []).append(row.value)
        elif row.kind == FIX_VERSION:
            fix_versions.append(row.value)
        elif row.kind == JIRA_PROJECT:
            projects.append(row.value)
        elif row.kind == VERSION_START:
            version_starts[row.repository] = row.value
        entries.append({"id": row.id, "kind": row.kind, "repository": row.repository or None, "value": row.value,
                        "addedAt": row.added_at.isoformat() if row.added_at else None})
    return {"branches": branches, "fixVersions": fix_versions, "jiraProjects": projects, "versionStarts": version_starts,
            "entries": entries}
