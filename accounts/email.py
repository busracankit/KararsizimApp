"""E-mail backend for Resend's HTTP API (https://resend.com/docs/api-reference/emails/send-email).

Uses only the standard library, so no extra package is needed.

Delivery errors are logged (visible in Vercel runtime logs) but never raised: a failed
password-reset e-mail must not turn into a 500 page or reveal whether an account exists.
"""
import json
import logging
import urllib.error
import urllib.request

from django.conf import settings
from django.core.mail.backends.base import BaseEmailBackend

logger = logging.getLogger(__name__)
RESEND_ENDPOINT = "https://api.resend.com/emails"


class ResendEmailBackend(BaseEmailBackend):
    def send_messages(self, email_messages):
        sent = 0
        for message in email_messages:
            payload = {
                "from": message.from_email or settings.DEFAULT_FROM_EMAIL,
                "to": list(message.to),
                "subject": message.subject,
                "text": message.body,
            }
            for alternative, mimetype in getattr(message, "alternatives", []):
                if mimetype == "text/html":
                    payload["html"] = alternative
            request = urllib.request.Request(
                RESEND_ENDPOINT,
                data=json.dumps(payload).encode(),
                headers={
                    "Authorization": f"Bearer {settings.RESEND_API_KEY}",
                    "Content-Type": "application/json",
                    "User-Agent": "kararsizim/1.0",
                },
                method="POST",
            )
            try:
                with urllib.request.urlopen(request, timeout=10) as response:
                    if 200 <= response.status < 300:
                        sent += 1
            except (urllib.error.URLError, TimeoutError) as error:
                detail = error.read().decode(errors="replace")[:300] if isinstance(error, urllib.error.HTTPError) else ""
                logger.error("Resend e-postası gönderilemedi: %s %s", error, detail)
        return sent
