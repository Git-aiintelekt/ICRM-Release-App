"""Short-lived caching of external responses, plus per-service health (last success, last error).

Every dashboard card and page reads through `cached()`, so one Jira/Bitbucket answer serves them all for
INTEGRATION_CACHE_SECONDS. "Refresh now" bumps a generation number, which makes every cached key stale at once
without touching anything else in the cache. Nothing is written to the database.
"""
import hashlib
import json
import threading
from datetime import datetime

from django.conf import settings
from django.core.cache import cache

from .http import IntegrationError

_GENERATION_KEY = "integrations:generation"
_HEALTH_KEY = "integrations:health:{}"
_lock = threading.Lock()


def _generation() -> int:
    return cache.get_or_set(_GENERATION_KEY, 1, timeout=None)


def invalidate() -> None:
    with _lock:
        try:
            cache.incr(_GENERATION_KEY)
        except ValueError:
            cache.set(_GENERATION_KEY, 2, timeout=None)


def _key(service: str, name: str, args) -> str:
    digest = hashlib.sha256(json.dumps(args, sort_keys=True, default=str).encode()).hexdigest()[:32]
    return f"integrations:{_generation()}:{service}:{name}:{digest}"


def cached(service: str, name: str, args, fetch):
    """Return the cached value for (service, name, args), or call fetch() and cache it.

    A successful fetch marks the service healthy; an IntegrationError marks it unhealthy and is re-raised
    (errors are never cached, so the next request tries again).
    """
    key = _key(service, name, args)
    hit = cache.get(key)
    if hit is not None:
        return hit
    try:
        value = fetch()
    except IntegrationError as exc:
        mark_error(service, exc)
        raise
    cache.set(key, value, timeout=settings.INTEGRATION_CACHE_SECONDS)
    mark_ok(service)
    return value


def health(service: str) -> dict:
    return cache.get(_HEALTH_KEY.format(service)) or {"lastSuccessAt": None, "lastErrorAt": None, "lastError": None}


def mark_ok(service: str) -> None:
    state = health(service)
    state["lastSuccessAt"] = datetime.now().isoformat(timespec="seconds")
    cache.set(_HEALTH_KEY.format(service), state, timeout=None)


def mark_error(service: str, exc: Exception) -> None:
    state = health(service)
    state["lastErrorAt"] = datetime.now().isoformat(timespec="seconds")
    state["lastError"] = str(exc)
    cache.set(_HEALTH_KEY.format(service), state, timeout=None)
