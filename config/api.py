"""API conventions shared by every endpoint, matching what python-backend (FastAPI) returned,
so the React app works unchanged:

  * request JSON is camelCase (converted to snake_case here); responses are built in camelCase
  * errors: {"detail": "..."}; validation errors: {"status": 400, "error": "Bad Request", "errors": {"field": "msg"}};
    not found: {"status": 404, "error": "Not Found", "message": "..."}
"""
import re
from datetime import datetime

from rest_framework import exceptions, permissions, status
from rest_framework.parsers import JSONParser
from rest_framework.response import Response
from rest_framework.throttling import SimpleRateThrottle
from rest_framework.views import exception_handler as drf_exception_handler

_CAMEL_RE = re.compile(r"(?<!^)(?=[A-Z])")


def to_snake(name: str) -> str:
    return _CAMEL_RE.sub("_", name).lower()


def to_camel(name: str) -> str:
    head, *rest = name.split("_")
    return head + "".join(part.title() for part in rest)


def _snake_keys(value):
    if isinstance(value, dict):
        return {to_snake(k) if isinstance(k, str) else k: _snake_keys(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_snake_keys(v) for v in value]
    return value


class CamelCaseJSONParser(JSONParser):
    def parse(self, stream, media_type=None, parser_context=None):
        return _snake_keys(super().parse(stream, media_type, parser_context))


class NotFound(exceptions.APIException):
    status_code = status.HTTP_404_NOT_FOUND
    default_detail = "Not found."


def _flatten(errors, prefix="") -> dict[str, str]:
    """{"items": [{"title": ["msg"]}]} -> {"items.0.title": "msg"}, keys in camelCase."""
    flat: dict[str, str] = {}
    if isinstance(errors, dict):
        for key, value in errors.items():
            name = "body" if key == "non_field_errors" else to_camel(str(key))
            flat.update(_flatten(value, f"{prefix}.{name}" if prefix else name))
    elif isinstance(errors, list):
        if all(not isinstance(e, (dict, list)) for e in errors):
            if errors:
                flat[prefix or "body"] = str(errors[0])
        else:
            for index, value in enumerate(errors):
                if value:
                    flat.update(_flatten(value, f"{prefix}.{index}"))
    else:
        flat[prefix or "body"] = str(errors)
    return flat


def exception_handler(exc, context):
    now = datetime.now().isoformat()
    if isinstance(exc, exceptions.ValidationError):
        return Response(
            {"timestamp": now, "status": 400, "error": "Bad Request", "errors": _flatten(exc.detail)},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if isinstance(exc, NotFound):
        return Response({"timestamp": now, "status": 404, "error": "Not Found", "message": str(exc.detail)}, status=404)
    if isinstance(exc, exceptions.NotAuthenticated):
        exc.detail = "Please sign in to continue."
    return drf_exception_handler(exc, context)


def bad_request(detail: str) -> exceptions.ParseError:
    """400 {"detail": "..."}, like FastAPI's HTTPException(400, detail)."""
    return exceptions.ParseError(detail)


def not_found(detail: str) -> exceptions.NotFound:
    """404 {"detail": "..."}, like FastAPI's HTTPException(404, detail)."""
    return exceptions.NotFound(detail)


class IsSignedIn(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user is not None


class IsAdmin(permissions.BasePermission):
    message = "This needs admin access (FULLADMIN security group)."

    def has_permission(self, request, view):
        if request.user is None:
            raise exceptions.NotAuthenticated()
        return request.user.is_admin


# ---- Rate limits on the sign-in endpoints, per client IP (rates: REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]) ----

class _ClientIPThrottle(SimpleRateThrottle):
    """Counts requests per client IP; NUM_PROXIES decides whether X-Forwarded-For is trusted."""

    def get_cache_key(self, request, view):
        return self.cache_format % {"scope": self.scope, "ident": self.get_ident(request)}


class LoginThrottle(_ClientIPThrottle):
    scope = "login"


class RegisterThrottle(_ClientIPThrottle):
    scope = "register"


class PasswordResetThrottle(_ClientIPThrottle):
    scope = "password_reset"
