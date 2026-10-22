"""What the Jira / Bitbucket screens are limited to. New table integration_scope (created by Django's migration).

Admins add these on Settings → Integrations. With none added for a repository, its screens show every branch; with
no fix version added, Jira counts and lists cover every fix version.
"""
from django.conf import settings
from django.db import models
from django.utils import timezone

BRANCH = "BRANCH"
FIX_VERSION = "FIX_VERSION"
# Jira projects added on top of JIRA_PROJECT_KEYS (.env), e.g. a new project started after deployment.
JIRA_PROJECT = "JIRA_PROJECT"
# Bitbucket repositories added on top of BITBUCKET_REPOSITORIES (.env), and .env ones an admin removed.
REPOSITORY = "REPOSITORY"
REPOSITORY_HIDDEN = "REPOSITORY_HIDDEN"
# When work on a release version started (repository = the version, value = YYYY-MM-DD), for the Jira ticket period.
VERSION_START = "VERSION_START"


class IntegrationScope(models.Model):
    kind = models.CharField(max_length=20, choices=[(BRANCH, "Bitbucket branch"), (FIX_VERSION, "Jira fix version"),
                                                    (JIRA_PROJECT, "Jira project"), (REPOSITORY, "Bitbucket repository"),
                                                    (REPOSITORY_HIDDEN, "Removed .env repository"),
                                                    (VERSION_START, "Version start date")])
    # Repository slug for a branch, the release version for a start date; empty otherwise.
    repository = models.CharField(max_length=100, blank=True, default="")
    value = models.CharField(max_length=200)
    # No database constraint: app_user is an existing table Django doesn't manage.
    added_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                 db_constraint=False, related_name="+")
    added_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "integration_scope"
        ordering = ["kind", "repository", "value"]
        constraints = [models.UniqueConstraint(fields=["kind", "repository", "value"], name="integration_scope_unique")]

    def __str__(self):
        return f"{self.repository}:{self.value}" if self.repository else self.value


class IntegrationCredential(models.Model):
    """A Jira / Bitbucket connection setting entered on Settings → Integrations (new table integration_credential).
    It takes the place of the .env value of the same name. Every value is encrypted (integrations/credentials.py)."""
    name = models.CharField(max_length=40, primary_key=True)
    encrypted_value = models.TextField()
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                   db_constraint=False, related_name="+")
    updated_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "integration_credential"

    def __str__(self):
        return self.name
