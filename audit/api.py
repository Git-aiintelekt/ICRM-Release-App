"""/api/admin/audit-log: filter by action ('JIRA' = every Jira view), user and date; paged.
/api/admin/audit-log.csv: the same filters, every matching entry (up to CSV_MAX_ROWS) as a CSV download."""
import csv
from datetime import datetime, time, timedelta

from django.http import HttpResponse

from rest_framework import serializers
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from config.api import IsAdmin, bad_request

from .models import ACTIONS, EXTRA_ACTIONS, JIRA_VIEW_ACTIONS, AuditLog


class AuditQuerySerializer(serializers.Serializer):
    action = serializers.CharField(required=False, allow_blank=True)
    username = serializers.CharField(required=False, allow_blank=True)
    date_from = serializers.DateField(required=False)
    date_to = serializers.DateField(required=False)
    limit = serializers.IntegerField(required=False, min_value=1, max_value=200, default=50)
    offset = serializers.IntegerField(required=False, min_value=0, default=0)


def entry_json(row: AuditLog) -> dict:
    return {
        "id": row.id,
        "userId": row.user_id,
        "username": row.username,
        "action": row.action,
        "target": row.target,
        "details": row.details,
        "ipAddress": row.ip_address,
        "userAgent": row.user_agent,
        "createdAt": row.created_at.isoformat(),
    }


CSV_MAX_ROWS = 10000
CSV_COLUMNS = ["createdAt", "username", "action", "target", "details", "ipAddress", "userAgent"]


def _filtered(request):
    """(matching rows newest first, validated query) for the filters in the query string."""
    params = request.query_params
    query = AuditQuerySerializer(data={
        "action": params.get("action", ""), "username": params.get("username", ""),
        **({"date_from": params["from"]} if params.get("from") else {}),
        **({"date_to": params["to"]} if params.get("to") else {}),
        **({"limit": params["limit"]} if params.get("limit") else {}),
        **({"offset": params["offset"]} if params.get("offset") else {}),
    })
    query.is_valid(raise_exception=True)
    q = query.validated_data
    rows = AuditLog.objects.all()
    action = q.get("action")
    if action == "JIRA":
        rows = rows.filter(action__in=JIRA_VIEW_ACTIONS)
    elif action:
        if action not in ACTIONS and action not in EXTRA_ACTIONS:
            raise bad_request(f"Unknown action {action!r}.")
        rows = rows.filter(action=action)
    if q.get("username"):
        rows = rows.filter(username__icontains=q["username"].strip().lower())
    if q.get("date_from"):
        rows = rows.filter(created_at__gte=datetime.combine(q["date_from"], time.min))
    if q.get("date_to"):
        rows = rows.filter(created_at__lt=datetime.combine(q["date_to"] + timedelta(days=1), time.min))
    return rows.order_by("-created_at", "-id"), q


@api_view(["GET"])
@permission_classes([IsAdmin])
def audit_log(request):
    rows, q = _filtered(request)
    page = rows[q["offset"]:q["offset"] + q["limit"]]
    return Response({"total": rows.count(), "entries": [entry_json(r) for r in page]})


def _csv_cell(value) -> str:
    # A cell starting with = + - @ would run as a formula in Excel (user agents and details come from clients).
    text = "" if value is None else str(value)
    return "'" + text if text[:1] in ("=", "+", "-", "@", "\t", "\r") else text


@api_view(["GET"])
@permission_classes([IsAdmin])
def audit_log_csv(request):
    rows, _ = _filtered(request)
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="audit-log-{datetime.now():%Y%m%d-%H%M}.csv"'
    response.write("\ufeff")  # BOM, so Excel reads the file as UTF-8
    writer = csv.writer(response)
    writer.writerow(CSV_COLUMNS)
    for row in rows[:CSV_MAX_ROWS]:
        entry = entry_json(row)
        writer.writerow([_csv_cell(entry[column]) for column in CSV_COLUMNS])
    return response
