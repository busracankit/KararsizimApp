"""Tiny database-backed rate limiter (no Redis needed; fine for prototype traffic).

Usage:
    if hit_rate_limit(request, "vote"):
        return ... 429 ...

Limits live in settings.RATE_LIMITS as {scope: (max_hits, window_seconds, by)} where
``by`` is "ip" or "user" ("user" falls back to IP for anonymous visitors).
"""
import random
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from .models import RateLimitHit


def client_ip(request):
    # Vercel sets these headers itself (client-supplied values are overwritten).
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip.strip()
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "")


def _key(request, by):
    if by == "user" and request.user.is_authenticated:
        return f"u{request.user.pk}"
    return f"ip:{client_ip(request)}"


def hit_rate_limit(request, scope):
    """Record one attempt for `scope`; return True if the caller is over the limit."""
    limits = getattr(settings, "RATE_LIMITS", {})
    if scope not in limits:
        return False
    max_hits, window, by = limits[scope]
    now = timezone.now()
    key = _key(request, by)
    recent = RateLimitHit.objects.filter(scope=scope, key=key, created_at__gte=now - timedelta(seconds=window))
    if recent.count() >= max_hits:
        return True
    RateLimitHit.objects.create(scope=scope, key=key)
    if random.random() < 0.02:  # occasional cleanup of old rows
        RateLimitHit.objects.filter(created_at__lt=now - timedelta(days=1)).delete()
    return False
