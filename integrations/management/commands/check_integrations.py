"""Test the live Jira Cloud and Bitbucket Cloud connections with the credentials in .env, read-only.

    .venv\\Scripts\\python manage.py check_integrations            # both
    .venv\\Scripts\\python manage.py check_integrations --jira     # Jira only
    .venv\\Scripts\\python manage.py check_integrations --bitbucket

Prints which settings are present (never their values), the Jira account name, per-project access, issue counts,
status/issue-type names and fix version names (to write JIRA_FIX_VERSION_MAP), and per-repository Bitbucket access.
Only read calls are made. Jira and Bitbucket are checked separately: a working Jira token says nothing about Bitbucket.
"""
from django.conf import settings
from django.core.management.base import BaseCommand

from integrations import bitbucket_client, jira_client
from integrations.bitbucket_client import BitbucketClient
from integrations.http import IntegrationError, NotFoundUpstream
from integrations.jira_client import JiraClient

SECRET_SETTINGS = {"JIRA_API_TOKEN", "BITBUCKET_API_TOKEN", "BITBUCKET_ACCESS_TOKEN"}


def status(exc) -> str:
    return f" (HTTP {exc.upstream_status})" if exc.upstream_status else ""


class Command(BaseCommand):
    help = "Read-only test of the Jira and Bitbucket connections configured in .env (secrets are never printed)."

    def add_arguments(self, parser):
        parser.add_argument("--jira", action="store_true", help="Check Jira only.")
        parser.add_argument("--bitbucket", action="store_true", help="Check Bitbucket only.")

    def handle(self, *args, **options):
        both = not options["jira"] and not options["bitbucket"]
        ok = True
        if both or options["jira"]:
            ok &= self.check_jira()
        if both or options["bitbucket"]:
            ok &= self.check_bitbucket()
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("All requested checks passed.") if ok else self.style.ERROR("Some checks failed (see above)."))

    # ---- output helpers ----

    def setting(self, name, optional=False):
        value = getattr(settings, name)
        if name in SECRET_SETTINGS:
            shown = f"set ({len(value)} characters)" if value else "MISSING"
        elif isinstance(value, list):
            shown = ", ".join(value) if value else "MISSING"
        else:
            shown = value or ("not set" if optional else "MISSING")
        style = self.style.ERROR if shown == "MISSING" else (lambda s: s)
        self.stdout.write(f"  {name:<24} {style(shown)}")

    def result(self, ok, text):
        self.stdout.write(f"  {self.style.SUCCESS('OK  ') if ok else self.style.ERROR('FAIL')} {text}")
        return ok

    # ---- Jira ----

    def check_jira(self) -> bool:
        self.stdout.write(self.style.MIGRATE_HEADING("Jira Cloud"))
        for name in ("JIRA_BASE_URL", "JIRA_CLOUD_ID", "JIRA_EMAIL", "JIRA_API_TOKEN", "JIRA_PROJECT_KEYS"):
            self.setting(name, optional=name == "JIRA_CLOUD_ID")
        if not jira_client.is_configured():
            return self.result(False, "Not configured. Missing: " + ", ".join(jira_client.missing_settings()))
        self.stdout.write("  API route: " + ("Atlassian API gateway (scoped token)" if jira_client.uses_gateway()
                                             else "site URL (classic token)"))
        client = JiraClient()
        try:
            checked = client.check()
        except IntegrationError as exc:
            return self.result(False, f"Authentication: {exc}{status(exc)}")
        ok = self.result(True, f"Authenticated as {checked['account']}" if checked["account"] else f"Authenticated. {checked['note']}")

        for key in client.keys:
            try:
                project = client._call("GET", f"/rest/api/3/project/{key}")
                count = client.count(f"project = {key}")
                ok &= self.result(True, f"{key}: {project.get('name')} - browse access, about {count} issues")
            except NotFoundUpstream:
                ok &= self.result(False, f"{key}: not found, or this account has no Browse permission (HTTP 404)")
            except IntegrationError as exc:
                ok &= self.result(False, f"{key}: {exc}{status(exc)}")

        try:
            meta = client.metadata()
            d = client.definitions(meta)
        except IntegrationError as exc:
            return self.result(False, f"Project metadata: {exc}{status(exc)}") and False
        self.stdout.write(f"  Issue types : {', '.join(meta['issueTypes'])}")
        self.stdout.write(f"  Statuses    : {', '.join(meta['statuses'])}")
        self.stdout.write(f"  Counted as resolved: {', '.join(d['resolvedStatuses']) or '-'}; closed: "
                          f"{', '.join(d['closedStatuses']) or '-'}; bugs: {', '.join(d['bugTypes']) or '-'}")
        for warning in d["warnings"]:
            self.stdout.write(self.style.WARNING(f"  Warning: {warning}"))
        recent = [v for v in meta["fixVersions"] if not v["archived"]][:25]
        self.stdout.write(f"  Fix versions ({len(meta['fixVersions'])} in total; most recent, not archived):")
        for v in recent:
            self.stdout.write(f"    {v['project']:<5} {v['name']:<30} {v['releaseDate'] or '-':<12} {'released' if v['released'] else 'unreleased'}")

        try:
            summary = client.summary()
            i = summary["issues"]
            self.stdout.write(f"  Dashboard counts: total {i['total']}, open {i['open']}, done {i['done']} "
                              f"(resolved {i['resolved']}, closed {i['closed']}, other {i['doneOther']})")
            ok &= self.result(True, "Dashboard summary query")
        except IntegrationError as exc:
            ok &= self.result(False, f"Dashboard summary query: {exc}{status(exc)}")
        return ok

    # ---- Bitbucket ----

    def check_bitbucket(self) -> bool:
        self.stdout.write(self.style.MIGRATE_HEADING("Bitbucket Cloud (checked separately from Jira)"))
        for name in ("BITBUCKET_WORKSPACE", "BITBUCKET_REPOSITORIES", "BITBUCKET_EMAIL", "BITBUCKET_API_TOKEN", "BITBUCKET_ACCESS_TOKEN"):
            self.setting(name)
        if not bitbucket_client.is_configured():
            return self.result(False, "Not configured. Missing: " + ", ".join(bitbucket_client.missing_settings()))
        client = BitbucketClient()
        ok = True
        for slug in bitbucket_client.repositories():
            try:
                repo = client.repository(slug)
                ok &= self.result(True, f"{repo['fullName']}: repository read (main branch {repo['mainBranch']})")
                commits = client.commits(slug, limit=1)["values"]
                ok &= self.result(True, f"{slug}: commits read" + (f" (latest {commits[0]['shortHash']}, {commits[0]['date']})" if commits else ""))
                client.pull_requests(slug, limit=1)
                ok &= self.result(True, f"{slug}: pull requests read")
            except IntegrationError as exc:
                ok &= self.result(False, f"{slug}: {exc}")
        return ok
