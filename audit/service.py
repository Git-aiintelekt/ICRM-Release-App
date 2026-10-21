"""Write audit log entries: who signed in, viewed Jira data, changed access, published or packaged releases."""
from .models import AuditLog


def client_ip(request) -> str | None:
    if request is None:
        return None
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    return forwarded.split(",")[0].strip() if forwarded else request.META.get("REMOTE_ADDR")


def record(request, action, user=None, *, username=None, target=None, details=None) -> AuditLog:
    ip = client_ip(request)
    agent = (request.META.get("HTTP_USER_AGENT") or "")[:255] or None if request is not None else None
    return AuditLog.objects.create(
        user_id=user.id if user else None,
        username=user.username if user else username,
        action=action,
        target=target[:255] if target else None,
        details=details[:500] if details else None,
        ip_address=ip[:45] if ip else None,
        user_agent=agent,
    )
