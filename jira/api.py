"""/api/jira-issues: admins and JIRA_VIEWER members only; every view is written to the audit log."""
from django.db.models import Count
from rest_framework import exceptions, permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from audit import models as audit
from audit.service import record
from config.api import NotFound

from .models import JiraIssue


class JiraAccess(permissions.BasePermission):
    message = "You don't have access to Jira issues. Ask an administrator to grant it in Settings."

    def has_permission(self, request, view):
        if request.user is None:
            raise exceptions.NotAuthenticated()
        if request.user.can_view_jira:
            return True
        record(request, audit.JIRA_ACCESS_DENIED, request.user, target=request.path)
        return False


def _seed_json(s) -> dict:
    return {"id": s.id, "type": s.type, "seedRef": s.seed_ref, "content": s.content, "displayOrder": s.display_order}


def _table_json(t) -> dict:
    return {
        "id": t.id, "type": t.type, "tableName": t.table_name, "primaryKeyField": t.primary_key_field,
        "primaryKeyValue": t.primary_key_value, "nameDescription": t.name_description, "seedRef": t.seed_ref,
        "content": t.content, "displayOrder": t.display_order,
    }


@api_view(["GET"])
@permission_classes([JiraAccess])
def list_issues(request):
    issues = JiraIssue.objects.annotate(
        seed_n=Count("seeds", distinct=True), table_n=Count("tables", distinct=True)
    ).order_by("jira_id")
    body = [
        {"jiraId": i.jira_id, "description": i.description, "link": i.link, "seedCount": i.seed_n, "tableCount": i.table_n}
        for i in issues
    ]
    record(request, audit.JIRA_LIST_VIEW, request.user, details=f"{len(body)} issues")
    return Response(body)


@api_view(["GET"])
@permission_classes([JiraAccess])
def issue_detail(request, jira_id):
    issue = JiraIssue.objects.filter(pk=jira_id).first()
    if issue is None:
        raise NotFound(f"Jira issue not found for {jira_id}")
    record(request, audit.JIRA_ISSUE_VIEW, request.user, target=issue.jira_id)
    return Response({
        "jiraId": issue.jira_id,
        "description": issue.description,
        "link": issue.link,
        "seeds": [_seed_json(s) for s in issue.seeds.order_by("display_order", "id")],
        "tables": [_table_json(t) for t in issue.tables.order_by("display_order", "id")],
    })
