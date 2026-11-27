"""Small security helpers: sign-in throttling.

Failed sign-ins are counted per (username, client IP) in Django's cache. After
LOGIN_FAILURE_LIMIT failures within LOGIN_LOCKOUT_SECONDS, that pair is refused
until the window passes. The message never says whether the account exists.

The default local-memory cache is per process. When hosting with more than one
process, set REDIS_URL so the counters are shared (see settings.CACHES).
"""
import hashlib

from django.conf import settings
from django.core.cache import cache


def client_ip(request):
    # REMOTE_ADDR is set by the server. Behind a trusted reverse proxy, configure the
    # proxy to pass the real address (see docs/OPERATIONS.md) instead of trusting headers here.
    return request.META.get("REMOTE_ADDR", "") or "unknown"


def _key(username, ip):
    raw = f"{(username or '').strip().lower()}|{ip}".encode()
    return "findit:login-fail:" + hashlib.sha256(raw).hexdigest()


def login_is_locked(username, ip):
    return cache.get(_key(username, ip), 0) >= settings.LOGIN_FAILURE_LIMIT


def record_login_failure(username, ip):
    key = _key(username, ip)
    try:
        count = cache.incr(key)
    except ValueError:
        cache.set(key, 1, settings.LOGIN_LOCKOUT_SECONDS)
        count = 1
    return count


def clear_login_failures(username, ip):
    cache.delete(_key(username, ip))
