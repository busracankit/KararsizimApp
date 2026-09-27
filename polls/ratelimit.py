"""Tiny database-backed rate limiter (no Redis needed; fine for prototype traffic).

Usage:
    if hit_rate_limit(request, "vote"):
        return ... 429 ...
    if hit_rate_limit(request, "visitor_vote_per_poll", suffix=poll.pk):   # one counter per poll
        ...

Limits live in settings.RATE_LIMITS as {scope: (max_hits, window_seconds, by)}:
    "ip"     – per client IP
    "user"   – per logged-in user (falls back to IP for visitors)
    "global" – only the suffix is the key (e.g. per account e-mail, whoever is trying)
"""
import hashlib
import random
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from .models import RateLimitHit


def client_ip(request):
    """Best-effort client IP.

    Proxy headers are only trusted behind a proxy that overwrites them (Vercel sets
    TRUST_PROXY_HEADERS). Vercel documents that it overwrites X-Forwarded-For, so that
    header is preferred; anywhere else a client could forge them, so REMOTE_ADDR is used.
    """
    if getattr(settings, "TRUST_PROXY_HEADERS", False):
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip.strip()
    return request.META.get("REMOTE_ADDR", "")


def _key(request, by, suffix):
    if by == "global":
        # Suffixes like e-mail addresses are hashed so no personal data sits in this table.
        return "k:" + hashlib.sha256(suffix.encode()).hexdigest()[:40]
    elif by == "user" and request.user.is_authenticated:
        base = f"u{request.user.pk}"
    else:
        base = f"ip:{client_ip(request)}"
    key = f"{base}:{suffix}" if suffix != "" else base
    return key[:80]  # column length


def hit_rate_limit(request, scope, suffix=""):
    """Record one attempt for `scope`; return True if the caller is over the limit.

    The attempt is written *before* counting, so concurrent requests always see each
    other and cannot slip past the limit together. A blocked attempt is removed again,
    so it doesn't extend the lock-out.
    """
    limits = getattr(settings, "RATE_LIMITS", {})
    if scope not in limits:
        return False
    max_hits, window, by = limits[scope]
    now = timezone.now()
    key = _key(request, by, str(suffix).strip().lower() if suffix != "" else "")
    hit = RateLimitHit.objects.create(scope=scope, key=key)
    recent = RateLimitHit.objects.filter(scope=scope, key=key, created_at__gte=now - timedelta(seconds=window))
    if recent.count() > max_hits:
        hit.delete()
        return True
    if random.random() < 0.02:  # occasional cleanup of old rows
        RateLimitHit.objects.filter(created_at__lt=now - timedelta(days=1)).delete()
    return False
