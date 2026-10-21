"""The existing audit_log table (unmanaged). user_id/username are copies, not a foreign key,
so entries survive user changes."""
from django.db import models
from django.utils import timezone

LOGIN = "LOGIN"
LOGIN_FAILED = "LOGIN_FAILED"
REGISTER = "REGISTER"
PASSWORD_RESET_REQUEST = "PASSWORD_RESET_REQUEST"
PASSWORD_RESET = "PASSWORD_RESET"
JIRA_LIST_VIEW = "JIRA_LIST_VIEW"
JIRA_ISSUE_VIEW = "JIRA_ISSUE_VIEW"
JIRA_ACCESS_DENIED = "JIRA_ACCESS_DENIED"
RELEASE_PUBLISH = "RELEASE_PUBLISH"
RELEASE_EDIT = "RELEASE_EDIT"
RELEASE_DELETE = "RELEASE_DELETE"
ACCESS_CHANGE = "ACCESS_CHANGE"
OFBIZ_PACKAGE = "OFBIZ_PACKAGE"

ACTIONS = [LOGIN, LOGIN_FAILED, REGISTER, PASSWORD_RESET_REQUEST, PASSWORD_RESET, JIRA_LIST_VIEW, JIRA_ISSUE_VIEW,
           JIRA_ACCESS_DENIED, RELEASE_PUBLISH, RELEASE_EDIT, RELEASE_DELETE, ACCESS_CHANGE, OFBIZ_PACKAGE]
JIRA_VIEW_ACTIONS = (JIRA_LIST_VIEW, JIRA_ISSUE_VIEW)

# Recorded and filterable, but deliberately not in the field's choices above: those are part of the migration
# state, so adding one there would need a migration. The column is a plain VARCHAR(40), and choices are only
# checked by forms, so these values need no schema or migration change.
INTEGRATION_REFRESH = "INTEGRATION_REFRESH"
RELEASE_EMAIL = "RELEASE_EMAIL"
INTEGRATION_SCOPE = "INTEGRATION_SCOPE"
LOGOUT_EVERYWHERE = "LOGOUT_EVERYWHERE"
EXTRA_ACTIONS = [INTEGRATION_REFRESH, RELEASE_EMAIL, INTEGRATION_SCOPE, LOGOUT_EVERYWHERE]


class AuditLog(models.Model):
    id = models.BigAutoField(primary_key=True)
    user_id = models.IntegerField(null=True, blank=True)
    username = models.CharField(max_length=100, null=True, blank=True)
    action = models.CharField(max_length=40, choices=[(a, a) for a in ACTIONS])
    target = models.CharField(max_length=255, null=True, blank=True)
    details = models.CharField(max_length=500, null=True, blank=True)
    ip_address = models.CharField("IP address", max_length=45, null=True, blank=True)
    user_agent = models.CharField(max_length=255, null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        managed = False
        db_table = "audit_log"
        ordering = ["-created_at", "-id"]
        verbose_name = "audit log entry"
        verbose_name_plural = "audit log"

    def __str__(self):
        return f"{self.created_at:%Y-%m-%d %H:%M} {self.action} {self.username or ''}".strip()
