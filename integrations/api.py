"""/api/integrations/...: live Jira and Bitbucket data, read through the server so tokens never reach the browser.

Reading: FULLADMIN or JIRA_VIEWER (the same rule, and the same audited denial, as /api/jira-issues).
Refreshing the cache: FULLADMIN, audited as INTEGRATION_REFRESH.
Scope: FULLADMIN can limit every screen to chosen Bitbucket branches (per repository) and Jira fix versions
(POST/DELETE /api/integrations/scope, audited as INTEGRATION_SCOPE). Requests for anything outside it get a 400.
Connection settings: FULLADMIN enters the Jira / Bitbucket URL, accounts and tokens (GET/PUT
/api/integrations/credentials, audited as INTEGRATION_SETTINGS); tokens are never sent back.
Release notes from Bitbucket: FULLADMIN lists the versions that have a release/ branch and drafts one version's
notes from its commits and Jira (release_generator.py). Nothing is saved: the draft is published like an upload.
Failures of one service come back as {"detail": "..."} with 400/404/502/503; the dashboard reports each section
separately, so one service being down doesn't hide the other.
"""
import functools
import re
from datetime import date

from django.conf import settings
from rest_framework import serializers
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from audit import models as audit
from audit.service import record
from config.api import IsAdmin
from jira.api import JiraAccess
from releases.models import ReleaseItem, ReleaseVersion

from . import bitbucket_client, cache, credentials, jira_client, release_generator, scope
from .bitbucket_client import BRANCH_RE, SLUG_RE, BitbucketClient
from .http import IntegrationError, NotFoundUpstream
from .jira_client import PROJECT_KEY_RE, JiraClient
from .models import BRANCH, FIX_VERSION, JIRA_PROJECT, REPOSITORY, REPOSITORY_HIDDEN, VERSION_START, IntegrationScope

TOKEN_RE = re.compile(r"^[A-Za-z0-9+/=_.:\-]{1,4096}$")
NAME_MAX = 100


def service_errors(view):
    """Answer an IntegrationError with its safe message instead of a 500."""
    @functools.wraps(view)
    def wrapper(request, *args, **kwargs):
        try:
            return view(request, *args, **kwargs)
        except IntegrationError as exc:
            return Response({"detail": str(exc)}, status=exc.status)
    return wrapper


def _names(request, param) -> list[str]:
    """Repeated (?status=A&status=B) or comma-free single values; each trimmed and length-checked."""
    values = [v.strip() for v in request.query_params.getlist(param) if v.strip()]
    for value in values:
        if len(value) > NAME_MAX or any(ord(c) < 32 for c in value):
            raise serializers.ValidationError({param: "Invalid value."})
    return values[:20]


class PageSerializer(serializers.Serializer):
    page = serializers.IntegerField(required=False, min_value=1, max_value=1000, default=1)
    limit = serializers.IntegerField(required=False, min_value=1, max_value=100, default=25)


def _paging(request) -> dict:
    s = PageSerializer(data={k: v for k, v in request.query_params.items() if k in ("page", "limit")})
    s.is_valid(raise_exception=True)
    return s.validated_data


def _fix_versions(request, sc) -> list[str]:
    """The fix versions asked for, which must be inside the admin's scope; none asked for = the whole scope."""
    asked, allowed = _names(request, "fixVersion"), sc["fixVersions"]
    if allowed and any(v not in allowed for v in asked):
        raise serializers.ValidationError({"fixVersion": "Only these Jira fix versions can be shown: " + ", ".join(allowed) + "."})
    return asked or allowed


def _branches(request, slug, sc) -> list[str]:
    """The branch asked for, which must be inside the admin's scope for this repository; none = the whole scope."""
    asked, allowed = (request.query_params.get("branch") or "").strip(), sc["branches"].get(slug, [])
    if asked and allowed and asked not in allowed:
        raise serializers.ValidationError({"branch": f"Only these branches of {slug} can be shown: " + ", ".join(allowed) + "."})
    return [asked] if asked else allowed


def _app_versions() -> list[str]:
    return list(ReleaseVersion.objects.order_by("-release_date").values_list("version", flat=True))


def _service_status(module, service) -> dict:
    return {"configured": module.is_configured(), "missingSettings": module.missing_settings(), **cache.health(service)}


def status_json(sc=None) -> dict:
    sc = sc or scope.current()
    return {
        "scope": sc,
        "jira": {**_service_status(jira_client, jira_client.SERVICE), "baseUrl": credentials.get("JIRA_BASE_URL") or None,
                 "projectKeys": jira_client.project_keys(), "baseProjectKeys": jira_client.base_project_keys()},
        "bitbucket": {**_service_status(bitbucket_client, bitbucket_client.SERVICE),
                      "workspace": credentials.get("BITBUCKET_WORKSPACE") or None, "repositories": bitbucket_client.repositories(),
                      "baseRepositories": bitbucket_client.base_repositories()},
        "cacheSeconds": settings.INTEGRATION_CACHE_SECONDS,
    }


# ---- status / refresh ----

@api_view(["GET"])
@permission_classes([JiraAccess])
def status(request):
    return Response(status_json())


@api_view(["POST"])
@permission_classes([IsAdmin])
def refresh(request):
    """Drop cached responses and test each configured service now."""
    cache.invalidate()
    checks, outcomes = {}, []
    for name, module, client in (("jira", jira_client, JiraClient), ("bitbucket", bitbucket_client, BitbucketClient)):
        if not module.is_configured():
            checks[name] = {"ok": False, "detail": "Not configured."}
            outcomes.append(f"{name}: not configured")
            continue
        try:
            checks[name] = {"ok": True, **client().check()}
            outcomes.append(f"{name}: ok")
        except IntegrationError as exc:
            cache.mark_error(module.SERVICE, exc)
            checks[name] = {"ok": False, "detail": str(exc)}
            outcomes.append(f"{name}: failed")
    # Outcome only: error texts stay out of the audit log.
    record(request, audit.INTEGRATION_REFRESH, request.user, target="integrations", details="; ".join(outcomes))
    return Response({**status_json(), "checks": checks})


# ---- Jira ----

@api_view(["GET"])
@permission_classes([JiraAccess])
@service_errors
def jira_filters(request):
    client = JiraClient()
    meta = client.metadata()
    d = client.definitions(meta)
    allowed = scope.current()["fixVersions"]
    # Admins: every name, to choose the scope from on Settings → Integrations.
    every = list(dict.fromkeys(v["name"] for v in meta["fixVersions"])) if request.user.is_admin else None
    if allowed:  # the version filter offers only the admin's chosen fix versions
        meta = {**meta, "fixVersions": [v for v in meta["fixVersions"] if v["name"] in allowed]}
    return Response({**meta, "scopeFixVersions": allowed, "allFixVersions": every, "definitions": {k: d[k] for k in ("resolvedStatuses", "closedStatuses", "bugTypes")},
                     "warnings": d["warnings"]})


@api_view(["GET"])
@permission_classes([JiraAccess])
@service_errors
def jira_summary(request):
    return Response(JiraClient().summary(_fix_versions(request, scope.current())))


ISSUE_STATES = ("open", "done", "resolved", "closed", "bug")


def _date(params, name) -> date | None:
    value = (params.get(name) or "").strip()
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise serializers.ValidationError({name: "Use a date like 2025-11-01."})


@api_view(["GET"])
@permission_classes([JiraAccess])
@service_errors
def jira_issues(request):
    params = request.query_params
    text = (params.get("q") or "").strip()
    if len(text) > 200:
        raise serializers.ValidationError({"q": "Search text is limited to 200 characters."})
    state = params.get("state") or None
    if state and state not in ISSUE_STATES:
        raise serializers.ValidationError({"state": "Must be one of " + ", ".join(ISSUE_STATES) + "."})
    token = params.get("pageToken") or None
    if token and not TOKEN_RE.match(token):
        raise serializers.ValidationError({"pageToken": "Invalid page token."})
    limit = _paging(request)["limit"]
    created_from, created_to = _date(params, "createdFrom"), _date(params, "createdTo")
    if created_from and created_to and created_from > created_to:
        raise serializers.ValidationError({"createdTo": "The end date is before the start date."})
    client = JiraClient()
    release = (params.get("release") or "").strip()
    keys = _release_keys(client, release) if release else None
    jql = client.build_jql(text=text, issue_types=_names(request, "type"), statuses=_names(request, "status"),
                           state=state, fix_versions=_fix_versions(request, scope.current()),
                           created_from=created_from, created_to=created_to, keys=keys)
    shown = jql.split(" ORDER BY ")[0]
    if keys:  # the key list is long; say what it is instead
        shown = shown.replace(f"key in {jira_client.jql_list(keys)}", f"key in (the {len(keys)} issues of {release})")
    return Response({**client.search(jql, page_token=token, limit=limit), "jql": shown})


def _release_keys(client, version: str) -> list[str]:
    """The Jira IDs of a published release (found in its release branch's commits) that Jira shows this account."""
    if not ReleaseVersion.objects.filter(version=version).exists():
        raise serializers.ValidationError({"release": f"No published release {version}."})
    keys = sorted({k.upper() for k in ReleaseItem.objects.filter(release_version__version=version)
                   .exclude(jira_id__isnull=True).exclude(jira_id="").values_list("jira_id", flat=True)})
    known = client.issue_statuses(keys)
    return [k for k in keys if k in known]


@api_view(["GET"])
@permission_classes([JiraAccess])
@service_errors
def jira_releases(request):
    return Response(JiraClient().release_summaries(_app_versions(), only=scope.current()["fixVersions"]))


# ---- Bitbucket ----

def with_jira_status(items: list[dict]) -> tuple[list[dict], str | None]:
    """Attach the live Jira status of every key found in the items. A missing status is reported, never guessed."""
    keys = {k for item in items for k in item["jiraKeys"]}
    if not keys:
        for item in items:
            item["jiraIssues"] = []
        return items, None
    warning, found = None, {}
    if not jira_client.is_configured():
        warning = "Jira is not configured, so the status of linked issues is unknown."
    else:
        try:
            found = JiraClient().issue_statuses(keys)
        except IntegrationError as exc:
            warning = f"Status of linked Jira issues is unavailable: {exc}"
    def linked(key):
        if key in found:
            return {k: found[key][k] for k in ("key", "summary", "status", "statusCategory", "issueType", "url")}
        # Unknown: either Jira wasn't asked (warning set) or it has no such issue visible to this account.
        return {"key": key, "summary": None, "status": None, "statusCategory": None, "issueType": None,
                "url": jira_client.browse_url(key) if credentials.get("JIRA_BASE_URL") else None, "notFound": warning is None}

    for item in items:
        item["jiraIssues"] = [linked(key) for key in item["jiraKeys"]]
    return items, warning


@api_view(["GET"])
@permission_classes([JiraAccess])
@service_errors
def bitbucket_repositories(request):
    client = BitbucketClient()
    repos = []
    for slug in bitbucket_client.repositories():
        try:
            repos.append(client.repository(slug))
        except IntegrationError as exc:
            repos.append({"slug": slug, "workspace": client.workspace, "error": str(exc)})
    return Response({"workspace": client.workspace, "repositories": repos, "branches": scope.current()["branches"]})


@api_view(["GET"])
@permission_classes([JiraAccess])
@service_errors
def bitbucket_branches(request, slug):
    q = (request.query_params.get("q") or "").strip() or None
    only = scope.current()["branches"].get(slug, [])
    return Response({**BitbucketClient().branches(slug, query=q, only=only, **_paging(request)), "scopeBranches": only})


@api_view(["GET"])
@permission_classes([JiraAccess])
@service_errors
def bitbucket_commits(request, slug):
    client = BitbucketClient()
    branches = _branches(request, slug, scope.current())
    data = client.commits(slug, branches=branches, exclude=release_generator.previous_branches(client, slug, branches),
                          **_paging(request))
    values, warning = with_jira_status([dict(c) for c in data["values"]])
    return Response({**data, "values": values, "jiraWarning": warning})


@api_view(["GET"])
@permission_classes([JiraAccess])
@service_errors
def bitbucket_pull_requests(request, slug):
    state = (request.query_params.get("state") or "").strip().upper() or None
    data = BitbucketClient().pull_requests(slug, state=state, branches=_branches(request, slug, scope.current()),
                                           **_paging(request))
    values, warning = with_jira_status([dict(p) for p in data["values"]])
    return Response({**data, "values": values, "jiraWarning": warning})


# ---- Dashboard: one request, every section from the shared cache ----

def _section(fn):
    try:
        return {"data": fn(), "error": None}
    except IntegrationError as exc:
        return {"data": None, "error": str(exc)}


def _status_counts(keys, issues) -> dict:
    """Open / done for these issue keys, done split into resolved, closed and other by status name (a split is None
    when no such status is configured). Keys Jira doesn't show count in the total only."""
    resolved_names, closed_names = set(settings.JIRA_RESOLVED_STATUSES), set(settings.JIRA_CLOSED_STATUSES)
    done = [k for k in keys if issues.get(k, {}).get("statusCategory") == "done"]
    statuses = [issues[k].get("status") for k in done]
    resolved = sum(1 for s in statuses if s in resolved_names)
    closed = sum(1 for s in statuses if s in closed_names and s not in resolved_names)
    return {"total": len(keys), "open": sum(1 for k in keys if k in issues and k not in done), "done": len(done),
            "resolved": resolved if resolved_names else None, "closed": closed if closed_names else None,
            "doneOther": len(done) - resolved - closed}


def _release_branch_counts(client, sc) -> list[dict]:
    """Per published release from a release/ branch in the scope: its Jira issues (the published items' Jira IDs, i.e.
    the ones found in the branch's commits) with their live status, all and bugs only. Newest version first."""
    rows = []
    for entry in release_generator.published_branches(sc["branches"]):
        keys = sorted({k.upper() for k in ReleaseItem.objects.filter(release_version__version=entry["version"])
                       .exclude(jira_id__isnull=True).exclude(jira_id="").values_list("jira_id", flat=True)})
        issues = client.issue_statuses(keys)
        bugs = [k for k in keys if (issues.get(k, {}).get("issueType") or "") in settings.JIRA_BUG_ISSUE_TYPES]
        rows.append({**entry, "issues": _status_counts(keys, issues), "bugs": _status_counts(bugs, issues),
                     "notFound": sum(1 for k in keys if k not in issues)})
    rows.sort(key=lambda r: tuple(int(p) for p in r["version"].split(".")), reverse=True)
    return rows


@api_view(["GET"])
@permission_classes([JiraAccess])
def dashboard(request):
    """The ticket counts of the published release branches (none published yet: no counts) and integration health."""
    body = {}
    sc = scope.current()
    if jira_client.is_configured():
        client = JiraClient()
        body["releaseBranches"] = _section(lambda: _release_branch_counts(client, sc))
    else:
        body["releaseBranches"] = {"data": None, "error": None, "notConfigured": True}
    if bitbucket_client.is_configured():
        # Nothing else here reads Bitbucket: one cached repository read keeps its health current.
        _section(lambda: BitbucketClient().repository(bitbucket_client.repositories()[0]))
    body["status"] = status_json(sc)
    return Response(body)


# ---- Scope: the branches and fix versions every screen is limited to, and added projects / repositories (admins) ----

class ScopeSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=[BRANCH, FIX_VERSION, JIRA_PROJECT, REPOSITORY, REPOSITORY_HIDDEN, VERSION_START])
    repository = serializers.CharField(max_length=100, required=False, allow_blank=True, default="")
    value = serializers.CharField(max_length=NAME_MAX)

    def validate(self, data):
        data["value"] = data["value"].strip()
        if not data["value"] or any(ord(c) < 32 for c in data["value"]):
            raise serializers.ValidationError({"value": "Invalid value."})
        if data["kind"] == BRANCH:
            if data["repository"] not in bitbucket_client.repositories():
                raise serializers.ValidationError({"repository": "Choose one of the configured repositories."})
            if not BRANCH_RE.match(data["value"]):
                raise serializers.ValidationError({"value": "Branch names contain only letters, digits, '.', '_', '-' and '/'."})
        elif data["kind"] == JIRA_PROJECT:
            data["repository"], data["value"] = "", data["value"].upper()
            if not PROJECT_KEY_RE.match(data["value"]):
                raise serializers.ValidationError({"value": "A Jira project key is 2-10 letters or digits, starting with a letter (e.g. CS)."})
            if data["value"] in jira_client.base_project_keys():
                raise serializers.ValidationError({"value": f"{data['value']} is already included (JIRA_PROJECT_KEYS)."})
        elif data["kind"] == VERSION_START:
            if data["repository"] not in _app_versions():
                raise serializers.ValidationError({"repository": "Choose one of the release versions."})
            try:
                data["value"] = date.fromisoformat(data["value"]).isoformat()
            except ValueError:
                raise serializers.ValidationError({"value": "Use a date like 2025-11-01."})
        elif data["kind"] in (REPOSITORY, REPOSITORY_HIDDEN):
            data["repository"] = ""
            if not SLUG_RE.match(data["value"]):
                raise serializers.ValidationError({"value": "A repository slug contains only letters, digits, '.', '_' and '-' "
                                                            "(the last part of its Bitbucket URL)."})
            if data["kind"] == REPOSITORY_HIDDEN and data["value"] not in bitbucket_client.base_repositories():
                raise serializers.ValidationError({"value": "Only a repository from BITBUCKET_REPOSITORIES can be removed this way."})
        else:
            data["repository"] = ""
        return data


def _check_exists(kind, repository, value) -> None:
    """Refuse a branch or fix version the service doesn't have (checked live, so a typo can't empty the screens)."""
    if kind == BRANCH:
        if not BitbucketClient().branches(repository, only=[value], limit=1)["values"]:
            raise serializers.ValidationError({"value": f"Branch {value} was not found in {repository}."})
    elif kind == REPOSITORY:
        if not BitbucketClient().exists(value):
            raise serializers.ValidationError({"value": f"Bitbucket has no repository {value} in this workspace, or this "
                                                        "account can't see it."})
    elif kind in (REPOSITORY_HIDDEN, VERSION_START):
        pass
    elif kind == JIRA_PROJECT:
        try:
            JiraClient()._call("GET", f"/rest/api/3/project/{value}")
        except NotFoundUpstream:
            raise serializers.ValidationError({"value": f"Jira has no project {value}, or this Jira account can't see it."})
    elif value not in {v["name"] for v in JiraClient().metadata()["fixVersions"]}:
        raise serializers.ValidationError({"value": f"Jira has no fix version named {value} in these projects."})


def _scope_label(row) -> str:
    if row.kind == VERSION_START:
        return f"start date {row.value} of version {row.repository}"
    return {BRANCH: "branch ", JIRA_PROJECT: "Jira project ", REPOSITORY: "repository ",
            REPOSITORY_HIDDEN: "hidden repository "}.get(row.kind, "fix version ") + str(row)


def _scope_changed(request, row, verb) -> Response:
    scope.forget()
    cache.invalidate()
    record(request, audit.INTEGRATION_SCOPE, request.user, target=str(row), details=f"{verb} {_scope_label(row)}")
    return Response(status_json(), status=201 if verb == "added" else 200)


def _drop_branches(slug) -> None:
    """A repository leaving the list takes its chosen branches with it."""
    IntegrationScope.objects.filter(kind=BRANCH, repository=slug).delete()


def _refuse_last_repository(slug) -> None:
    if bitbucket_client.repositories() == [slug]:
        raise serializers.ValidationError({"value": "At least one repository must stay; add another one first."})


def _repository_add(request, slug):
    """Add a repository, or bring back a .env one that was removed."""
    hidden = IntegrationScope.objects.filter(kind=REPOSITORY_HIDDEN, value=slug).first()
    if hidden is not None:
        hidden.delete()
        hidden.kind = REPOSITORY  # for the audit text: the repository is back
        return _scope_changed(request, hidden, "added")
    if slug in bitbucket_client.repositories():
        raise serializers.ValidationError({"value": f"{slug} is already in the list."})
    _check_exists(REPOSITORY, "", slug)
    row = IntegrationScope.objects.create(kind=REPOSITORY, value=slug, added_by=request.user)
    return _scope_changed(request, row, "added")


@api_view(["POST"])
@permission_classes([IsAdmin])
@service_errors
def scope_add(request):
    s = ScopeSerializer(data=request.data)
    s.is_valid(raise_exception=True)
    kind, repository, value = s.validated_data["kind"], s.validated_data["repository"], s.validated_data["value"]
    if kind == REPOSITORY:
        return _repository_add(request, value)
    if kind == VERSION_START:  # one start date per version: a new one replaces the old
        IntegrationScope.objects.filter(kind=VERSION_START, repository=repository).delete()
    if IntegrationScope.objects.filter(kind=kind, repository=repository, value=value).exists():
        done = "removed" if kind == REPOSITORY_HIDDEN else "added"
        raise serializers.ValidationError({"value": f"{value} is already {done}."})
    if kind == REPOSITORY_HIDDEN:
        _refuse_last_repository(value)
        _drop_branches(value)
    _check_exists(kind, repository, value)
    row = IntegrationScope.objects.create(kind=kind, repository=repository, value=value, added_by=request.user)
    return _scope_changed(request, row, "added")


@api_view(["DELETE"])
@permission_classes([IsAdmin])
def scope_remove(request, scope_id):
    row = IntegrationScope.objects.filter(pk=scope_id).first()
    if row is None:
        return Response({"detail": "Not found."}, status=404)
    if row.kind == REPOSITORY:
        _refuse_last_repository(row.value)
        _drop_branches(row.value)
    row.delete()
    return _scope_changed(request, row, "removed")


# ---- connection settings (Jira / Bitbucket accounts and tokens) ----

URL_RE = re.compile(r"^https://[^\s/?#]+(/[^\s?#]*)?$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
SECRET_RE = re.compile(r"^\S{1,4096}$")
CREDENTIAL_RULES = {
    "JIRA_BASE_URL": (URL_RE, "Use the site address, e.g. https://your-site.atlassian.net"),
    "JIRA_EMAIL": (EMAIL_RE, "Use the email of the Atlassian account."),
    "BITBUCKET_WORKSPACE": (SLUG_RE, "Use the workspace ID from the Bitbucket URL (letters, digits, . _ -)."),
    "BITBUCKET_EMAIL": (EMAIL_RE, "Use the email of the Atlassian account."),
}


def credentials_json() -> list[dict]:
    """Each setting, where its value comes from, and the value itself except for secrets."""
    return [{"name": name, "label": label, "secret": secret, "source": credentials.source(name),
             "value": None if secret else (credentials.get(name) or None)}
            for name, label, secret in credentials.FIELDS]


class CredentialsSerializer(serializers.Serializer):
    """Each setting is optional: left out = unchanged, empty or null = remove the app value (back to .env)."""

    def get_fields(self):
        return {name.lower(): serializers.CharField(required=False, allow_blank=True, allow_null=True, max_length=4096)
                for name in credentials.NAMES}

    def validate(self, data):
        errors = {}
        for key, value in data.items():
            name = key.upper()
            if not value:
                continue
            pattern, message = CREDENTIAL_RULES.get(name, (SECRET_RE, "Paste the token without spaces."))
            if len(value) > (200 if name == "JIRA_BASE_URL" else 191 if name.endswith("EMAIL") else 4096)                     or not pattern.match(value):
                errors[key] = message
        if errors:
            raise serializers.ValidationError(errors)
        return {key.upper(): (value or "").rstrip("/") if key == "jira_base_url" else value or ""
                for key, value in data.items()}


@api_view(["GET", "PUT"])
@permission_classes([IsAdmin])
def credentials_settings(request):
    if request.method == "GET":
        return Response({"fields": credentials_json()})
    s = CredentialsSerializer(data=request.data)
    s.is_valid(raise_exception=True)
    changed = credentials.save(s.validated_data, request.user)
    if changed:
        cache.invalidate()  # answers fetched with the old account must not be shown any more
        # Names only: values, and tokens above all, stay out of the audit log.
        record(request, audit.INTEGRATION_SETTINGS, request.user, target="integrations",
               details="changed " + ", ".join(changed))
    return Response({"fields": credentials_json(), "status": status_json()})


# ---- release notes drafted from Bitbucket release branches ----

@api_view(["GET"])
@permission_classes([IsAdmin])
@service_errors
def release_versions(request):
    return Response(release_generator.versions())


class GenerateSerializer(serializers.Serializer):
    version = serializers.RegexField(r"^\d+(\.\d+){0,5}$", max_length=50)


@api_view(["POST"])
@permission_classes([IsAdmin])
@service_errors
def release_draft(request):
    s = GenerateSerializer(data=request.data)
    s.is_valid(raise_exception=True)
    return Response(release_generator.generate(s.validated_data["version"]))

