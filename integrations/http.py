"""JSON over HTTPS for the Jira and Bitbucket clients (standard library only, no extra dependency).

Errors are raised as IntegrationError subclasses with a message that is safe to show in the UI: it never contains
the Authorization header or the token.
"""
import base64
import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request

from django.conf import settings

log = logging.getLogger(__name__)

# A 429 is retried once when the server asks to wait at most this long; otherwise it is reported.
MAX_RETRY_AFTER_SECONDS = 10


class IntegrationError(Exception):
    """An external service call failed. `status` is the HTTP status this app answers with."""

    status = 502

    def __init__(self, message, *, upstream_status=None):
        super().__init__(message)
        self.upstream_status = upstream_status


class NotConfigured(IntegrationError):
    status = 503


class AuthFailed(IntegrationError):
    status = 502


class RateLimited(IntegrationError):
    status = 503


class BadQuery(IntegrationError):
    """The service rejected what was asked for (e.g. a filter value it doesn't know)."""

    status = 400


class NotFoundUpstream(IntegrationError):
    status = 404


def basic_auth(user: str, secret: str) -> str:
    return "Basic " + base64.b64encode(f"{user}:{secret}".encode()).decode()


def _error_text(body: bytes) -> str:
    """Jira: {"errorMessages": [...], "errors": {...}}; Bitbucket: {"error": {"message": ...}}."""
    try:
        data = json.loads(body.decode("utf-8", errors="replace"))
    except ValueError:
        return ""
    if not isinstance(data, dict):
        return ""
    parts = list(data.get("errorMessages") or [])
    if isinstance(data.get("errors"), dict):
        parts += [f"{k}: {v}" for k, v in data["errors"].items()]
    if isinstance(data.get("error"), dict) and data["error"].get("message"):
        parts.append(str(data["error"]["message"]))
    return "; ".join(str(p) for p in parts)[:400]


def request_json(service: str, method: str, url: str, *, auth: str, params=None, body=None, opener=None):
    """Call `url` and return the decoded JSON. `opener` is urllib.request.urlopen (replaced in tests)."""
    opener = opener or urllib.request.urlopen
    if params:
        url = f"{url}?{urllib.parse.urlencode(params, doseq=True)}"
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Accept": "application/json", "Authorization": auth}
    if data is not None:
        headers["Content-Type"] = "application/json"

    for attempt in (1, 2):
        req = urllib.request.Request(url, data=data, method=method, headers=headers)
        started = time.monotonic()
        try:
            with opener(req, timeout=settings.INTEGRATION_TIMEOUT_SECONDS) as response:
                raw = response.read()
            log.info("%s %s %s -> ok in %.0f ms", service, method, url.split("?")[0], (time.monotonic() - started) * 1000)
            return json.loads(raw) if raw else None
        except urllib.error.HTTPError as exc:
            status = exc.code
            detail = _error_text(exc.read() or b"")
            retry_after = exc.headers.get("Retry-After") if exc.headers else None
            log.warning("%s %s %s -> HTTP %s", service, method, url.split("?")[0], status)
            if status == 429:
                wait = int(retry_after) if (retry_after or "").isdigit() else None
                if attempt == 1 and wait is not None and wait <= MAX_RETRY_AFTER_SECONDS:
                    time.sleep(wait)
                    continue
                raise RateLimited(f"{service} is rate limiting requests. Try again in a minute.", upstream_status=429)
            if status == 401:
                raise AuthFailed(f"{service} rejected the credentials. Check the {service} connection on Settings → Integrations.", upstream_status=401)
            if status == 403:
                raise AuthFailed(
                    f"{service} denied access. The configured account or token lacks permission for this data.",
                    upstream_status=403,
                )
            if status == 404:
                raise NotFoundUpstream(f"{service}: not found. {detail}".strip(), upstream_status=404)
            if status == 400:
                raise BadQuery(f"{service} rejected the request. {detail}".strip(), upstream_status=400)
            raise IntegrationError(f"{service} returned an error (HTTP {status}). Try again later.", upstream_status=status)
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            reason = getattr(exc, "reason", exc)
            log.warning("%s %s %s -> %s", service, method, url.split("?")[0], type(reason).__name__)
            raise IntegrationError(f"Could not reach {service} ({type(reason).__name__}). Check the network and the base URL.")
        except ValueError:
            raise IntegrationError(f"{service} returned a response that is not JSON.")
    raise RateLimited(f"{service} is rate limiting requests. Try again in a minute.", upstream_status=429)
