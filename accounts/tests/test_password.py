import json
import re
from unittest import mock

from django.core import mail
from django.core.mail import EmailMultiAlternatives
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.email import ResendEmailBackend
from accounts.models import User

PASSWORD = "guclu-parola-123"


class PasswordResetTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("ayse", "ayse@example.com", PASSWORD)

    def test_login_page_links_to_reset(self):
        self.assertContains(self.client.get(reverse("login")), reverse("password_reset"))

    def test_full_reset_flow(self):
        r = self.client.post(reverse("password_reset"), {"email": "AYSE@example.com"})
        self.assertRedirects(r, reverse("password_reset_done"))
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.to, ["ayse@example.com"])
        self.assertIn("@ayse", message.body)
        self.assertEqual(message.alternatives[0][1], "text/html")
        link = re.search(r"http://testserver(/parola-sifirla/\S+/)", message.body).group(1)

        r = self.client.get(link, follow=True)  # Django swaps the token for a session value
        self.assertContains(r, "Yeni parolanı belirle")
        r = self.client.post(r.redirect_chain[-1][0], {"new_password1": "yepyeni-parola-456", "new_password2": "yepyeni-parola-456"})
        self.assertRedirects(r, reverse("password_reset_complete"))
        self.assertTrue(self.client.login(email="ayse@example.com", password="yepyeni-parola-456"))

    def test_unknown_email_gets_same_page_and_no_mail(self):
        r = self.client.post(reverse("password_reset"), {"email": "yok@example.com"})
        self.assertRedirects(r, reverse("password_reset_done"))
        self.assertEqual(len(mail.outbox), 0)

    def test_invalid_link(self):
        r = self.client.get(reverse("password_reset_confirm", args=["MQ", "yanlis-token"]))
        self.assertContains(r, "Link geçersiz")

    @override_settings(RATE_LIMITS={"password_reset": (1, 3600, "ip")})
    def test_rate_limited(self):
        self.client.post(reverse("password_reset"), {"email": "ayse@example.com"})
        r = self.client.post(reverse("password_reset"), {"email": "ayse@example.com"})
        self.assertContains(r, "Çok fazla deneme")
        self.assertEqual(len(mail.outbox), 1)

    def test_password_change(self):
        self.client.force_login(self.user)
        self.assertContains(self.client.get(reverse("user_profile", args=["ayse"])), reverse("password_change"))
        r = self.client.post(reverse("password_change"), {
            "old_password": PASSWORD, "new_password1": "baska-parola-789", "new_password2": "baska-parola-789",
        })
        self.assertRedirects(r, reverse("password_change_done"))
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("baska-parola-789"))


@override_settings(RESEND_API_KEY="re_test", DEFAULT_FROM_EMAIL="Kararsızım <onboarding@resend.dev>")
class ResendBackendTests(TestCase):
    def test_posts_json_to_resend(self):
        message = EmailMultiAlternatives("Konu", "Düz metin", to=["a@example.com"])
        message.attach_alternative("<b>HTML</b>", "text/html")
        response = mock.MagicMock(status=200)
        response.__enter__.return_value = response
        with mock.patch("urllib.request.urlopen", return_value=response) as urlopen:
            sent = ResendEmailBackend().send_messages([message])
        self.assertEqual(sent, 1)
        request = urlopen.call_args[0][0]
        self.assertEqual(request.full_url, "https://api.resend.com/emails")
        self.assertEqual(request.headers["Authorization"], "Bearer re_test")
        body = json.loads(request.data)
        self.assertEqual(body["to"], ["a@example.com"])
        self.assertEqual(body["html"], "<b>HTML</b>")
        self.assertEqual(body["from"], "Kararsızım <onboarding@resend.dev>")

    def test_errors_are_logged_not_raised(self):
        import urllib.error
        message = EmailMultiAlternatives("Konu", "Metin", to=["a@example.com"])
        with mock.patch("urllib.request.urlopen", side_effect=urllib.error.URLError("down")), \
                self.assertLogs("accounts.email", level="ERROR"):
            self.assertEqual(ResendEmailBackend().send_messages([message]), 0)
