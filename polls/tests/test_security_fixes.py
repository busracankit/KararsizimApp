"""Regression tests for the security review (27.09.2026)."""
from concurrent.futures import ThreadPoolExecutor
from unittest import mock

from django.db import IntegrityError
from django.test import Client, TestCase, TransactionTestCase, override_settings
from django.urls import reverse

from accounts.models import User
from polls.models import RateLimitHit, Vote
from polls.ratelimit import hit_rate_limit

from .test_polls import PASSWORD, make_poll

JSON = {"HTTP_ACCEPT": "application/json"}


class VisitorVoteCapTests(TestCase):
    def setUp(self):
        self.author = User.objects.create_user("ayse", "ayse@example.com", PASSWORD)
        self.poll = make_poll(self.author)
        self.url = reverse("poll_vote", args=[self.poll.pk])
        self.option = self.poll.options.first().pk

    def vote(self, ip, member=None):
        c = Client(REMOTE_ADDR=ip)
        if member:
            c.force_login(member)
        c.get("/")
        return c.post(self.url, {"option_id": self.option}, **JSON)

    def test_scripted_visitor_votes_capped_per_poll_and_network(self):
        codes = [self.vote("7.7.7.7").status_code for _ in range(5)]
        self.assertEqual(codes, [200, 200, 200, 429, 429])
        self.assertEqual(self.vote("7.7.7.7").json()["error"], "login_required")
        self.assertEqual(Vote.objects.count(), 3)

    def test_cap_is_per_poll(self):
        for _ in range(3):
            self.vote("7.7.7.7")
        other = make_poll(self.author, "Başka bir soru burada?")
        c = Client(REMOTE_ADDR="7.7.7.7"); c.get("/")
        r = c.post(reverse("poll_vote", args=[other.pk]), {"option_id": other.options.first().pk}, **JSON)
        self.assertEqual(r.status_code, 200)

    def test_members_are_not_capped(self):
        for _ in range(3):
            self.vote("7.7.7.7")
        member = User.objects.create_user("mehmet", "m@example.com", PASSWORD)
        self.assertEqual(self.vote("7.7.7.7", member=member).status_code, 200)

    def test_changing_own_vote_is_not_capped(self):
        c = Client(REMOTE_ADDR="7.7.7.7"); c.get("/")
        c.post(self.url, {"option_id": self.option}, **JSON)
        for _ in range(3):
            self.vote("7.7.7.7")  # other visitors on the same network use up the cap
        second = self.poll.options.last().pk
        r = c.post(self.url, {"option_id": second, "change": "1"}, **JSON)
        self.assertEqual(r.status_code, 200)


class AdminLoginRateLimitTests(TestCase):
    def setUp(self):
        User.objects.create_superuser("admin", "admin@example.com", PASSWORD)

    @override_settings(RATE_LIMITS={"login": (3, 900, "ip"), "login_account": (100, 900, "global")})
    def test_admin_login_limited_per_ip(self):
        c = Client(REMOTE_ADDR="8.8.8.8")
        codes = [c.post("/admin/login/", {"username": "admin", "password": f"yanlis{i}"}).status_code for i in range(4)]
        self.assertEqual(codes, [200, 200, 200, 429])
        r = c.post("/admin/login/", {"username": "admin", "password": PASSWORD})
        self.assertEqual(r.status_code, 429)  # even the right password is refused while locked

    @override_settings(RATE_LIMITS={"login": (100, 900, "ip"), "login_account": (2, 900, "global")})
    def test_admin_login_limited_per_account_across_ips(self):
        codes = [
            Client(REMOTE_ADDR=f"10.0.0.{i}").post("/admin/login/", {"username": "admin", "password": "x"}).status_code
            for i in range(3)
        ]
        self.assertEqual(codes, [200, 200, 429])

    def test_admin_login_still_works(self):
        r = Client().post("/admin/login/?next=/admin/", {"username": "admin", "password": PASSWORD})
        self.assertRedirects(r, "/admin/", fetch_redirect_response=False)


class SiteLoginPerAccountTests(TestCase):
    @override_settings(RATE_LIMITS={"login": (100, 900, "ip"), "login_account": (2, 900, "global")})
    def test_distributed_guessing_limited_per_account(self):
        User.objects.create_user("ayse", "ayse@example.com", PASSWORD)
        codes = [
            Client(REMOTE_ADDR=f"10.0.1.{i}").post(reverse("login"), {"email": "AYSE@example.com", "password": "x"}).status_code
            for i in range(3)
        ]
        self.assertEqual(codes, [200, 200, 429])
        other = Client(REMOTE_ADDR="10.0.1.99").post(reverse("login"), {"email": "baska@example.com", "password": "x"})
        self.assertEqual(other.status_code, 200)

    def test_account_key_does_not_store_email(self):
        Client().post(reverse("login"), {"email": "gizli@example.com", "password": "x"})
        keys = list(RateLimitHit.objects.filter(scope="login_account").values_list("key", flat=True))
        self.assertTrue(keys)
        self.assertFalse(any("gizli" in k for k in keys))


class RateLimiterBehaviourTests(TestCase):
    @override_settings(RATE_LIMITS={"x": (2, 60, "ip")})
    def test_blocked_attempts_do_not_extend_lockout(self):
        from django.test import RequestFactory
        from django.contrib.auth.models import AnonymousUser
        request = RequestFactory().get("/", REMOTE_ADDR="1.2.3.4")
        request.user = AnonymousUser()
        results = [hit_rate_limit(request, "x") for _ in range(5)]
        self.assertEqual(results, [False, False, True, True, True])
        self.assertEqual(RateLimitHit.objects.filter(scope="x").count(), 2)


@override_settings(RATE_LIMITS={"burst": (3, 60, "ip")})
class RateLimiterConcurrencyTests(TransactionTestCase):
    def test_parallel_requests_cannot_exceed_limit(self):
        from django.contrib.auth.models import AnonymousUser
        from django.db import connection
        from django.test import RequestFactory

        if connection.vendor == "sqlite":
            self.skipTest("SQLite serialises writes; the race only exists on Postgres")

        def attempt(_):
            request = RequestFactory().get("/", REMOTE_ADDR="5.5.5.5")
            request.user = AnonymousUser()
            try:
                return hit_rate_limit(request, "burst")
            finally:
                connection.close()

        with ThreadPoolExecutor(max_workers=10) as pool:
            allowed = [r for r in pool.map(attempt, range(10)) if r is False]
        self.assertLessEqual(len(allowed), 3)


class RegisterRaceTests(TestCase):
    def test_duplicate_signup_race_shows_form_error_not_500(self):
        data = {"username": "ayse", "email": "ayse@example.com", "password1": PASSWORD, "password2": PASSWORD}
        with mock.patch("accounts.forms.RegisterForm.save", side_effect=IntegrityError("duplicate")):
            r = self.client.post(reverse("register"), data)
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "az önce alındı")


class CacheableResponseCookieTests(TestCase):
    def test_share_image_is_cacheable_and_sets_no_cookie(self):
        author = User.objects.create_user("ayse", "ayse@example.com", PASSWORD)
        poll = make_poll(author)
        r = Client().get(reverse("poll_share_image", args=[poll.pk]))
        self.assertIn("public", r["Cache-Control"])
        self.assertNotIn("kararsizim_vid", r.cookies)
        self.assertNotIn("Set-Cookie", str(r.serialize_headers()))

    def test_html_pages_still_set_voter_cookie(self):
        self.assertIn("kararsizim_vid", Client().get("/").cookies)


class HostSettingsTests(TestCase):
    def test_vercel_hostnames_are_added_exactly(self):
        import importlib
        import os

        import config.settings as settings_module

        env = {
            "DJANGO_DEBUG": "True",
            "DJANGO_ALLOWED_HOSTS": "kararsizim-liard.vercel.app",
            "DJANGO_CSRF_TRUSTED_ORIGINS": "https://kararsizim-liard.vercel.app",
            "VERCEL_URL": "kararsizim-abc123-team.vercel.app",
            "VERCEL_PROJECT_PRODUCTION_URL": "kararsizim-liard.vercel.app",
        }
        with mock.patch.dict(os.environ, env):
            fresh = importlib.reload(settings_module)
            hosts, origins = list(fresh.ALLOWED_HOSTS), list(fresh.CSRF_TRUSTED_ORIGINS)
        importlib.reload(settings_module)
        self.assertEqual(hosts, ["kararsizim-liard.vercel.app", "kararsizim-abc123-team.vercel.app"])
        self.assertIn("https://kararsizim-abc123-team.vercel.app", origins)
        self.assertFalse(any("*" in h or h.startswith(".") for h in hosts))
