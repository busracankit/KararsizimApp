from django.test import Client, TestCase, override_settings
from django.urls import reverse

from accounts.models import User
from polls.models import Poll, RateLimitHit
from polls.ratelimit import client_ip

from .test_polls import PASSWORD, make_poll

JSON = {"HTTP_ACCEPT": "application/json"}


@override_settings(RATE_LIMITS={"vote": (2, 600, "ip"), "poll_create": (1, 3600, "user"), "login": (2, 900, "ip"), "register": (1, 3600, "ip")})
class RateLimitTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("ayse", "ayse@example.com", PASSWORD)

    def test_votes_limited_per_ip(self):
        polls = [make_poll(self.user, f"Soru numarası {i}?") for i in range(3)]
        codes = []
        for poll in polls:
            c = Client(REMOTE_ADDR="1.2.3.4")
            c.get("/")
            r = c.post(reverse("poll_vote", args=[poll.pk]), {"option_id": poll.options.first().pk}, **JSON)
            codes.append(r.status_code)
        self.assertEqual(codes, [200, 200, 429])
        other = Client(REMOTE_ADDR="5.6.7.8")
        other.get("/")
        r = other.post(reverse("poll_vote", args=[polls[2].pk]), {"option_id": polls[2].options.first().pk}, **JSON)
        self.assertEqual(r.status_code, 200)

    def test_rate_limited_json_body(self):
        poll = make_poll(self.user)
        c = Client(); c.get("/")
        for _ in range(2):
            c.post(reverse("poll_vote", args=[poll.pk]), {"option_id": poll.options.first().pk}, **JSON)
        r = c.post(reverse("poll_vote", args=[poll.pk]), {"option_id": poll.options.first().pk}, **JSON)
        self.assertEqual(r.json(), {"ok": False, "error": "rate_limited"})

    def test_poll_create_limited_per_user(self):
        self.client.force_login(self.user)
        data = {"question": "Birinci soru burada?", "options": ["A1", "B2"]}
        self.client.post(reverse("poll_create"), data)
        r = self.client.post(reverse("poll_create"), {**data, "question": "İkinci soru burada?"})
        self.assertEqual(r.status_code, 429)
        self.assertContains(r, "çok fazla anket", status_code=429)
        self.assertEqual(Poll.objects.count(), 1)

    def test_login_limited(self):
        for _ in range(2):
            self.client.post(reverse("login"), {"email": "ayse@example.com", "password": "yanlis"})
        r = self.client.post(reverse("login"), {"email": "ayse@example.com", "password": PASSWORD})
        self.assertEqual(r.status_code, 429)
        self.assertFalse(r.wsgi_request.user.is_authenticated)

    def test_register_limited(self):
        data = {"username": "yeni1", "email": "y1@example.com", "password1": PASSWORD, "password2": PASSWORD}
        Client().post(reverse("register"), data)
        r = Client().post(reverse("register"), {**data, "username": "yeni2", "email": "y2@example.com"})
        self.assertEqual(r.status_code, 429)
        self.assertFalse(User.objects.filter(username="yeni2").exists())

    def test_client_ip_uses_proxy_headers_only_when_trusted(self):
        from django.test import RequestFactory
        rf = RequestFactory()
        spoofed = rf.get("/", HTTP_X_FORWARDED_FOR="8.8.8.8, 10.0.0.1", HTTP_X_REAL_IP="9.9.9.9", REMOTE_ADDR="1.1.1.1")
        with self.settings(TRUST_PROXY_HEADERS=False):
            self.assertEqual(client_ip(spoofed), "1.1.1.1")
        with self.settings(TRUST_PROXY_HEADERS=True):
            self.assertEqual(client_ip(spoofed), "8.8.8.8")  # Vercel overwrites X-Forwarded-For
            self.assertEqual(client_ip(rf.get("/", HTTP_X_REAL_IP="9.9.9.9", REMOTE_ADDR="1.1.1.1")), "9.9.9.9")

    def test_hits_are_recorded(self):
        self.client.post(reverse("login"), {"email": "x@example.com", "password": "y"})
        self.assertEqual(RateLimitHit.objects.filter(scope="login").count(), 1)
