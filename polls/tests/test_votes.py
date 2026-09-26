import uuid

from django.db import IntegrityError, transaction
from django.test import Client, TestCase
from django.urls import reverse

from accounts.models import User
from polls.middleware import VOTER_COOKIE_NAME
from polls.models import Vote
from polls.services import percent

from .test_polls import PASSWORD, make_poll

JSON = {"HTTP_ACCEPT": "application/json"}


class VoteTestCase(TestCase):
    def setUp(self):
        self.author = User.objects.create_user("ayse", "ayse@example.com", PASSWORD)
        self.poll = make_poll(self.author, options=("Sinema", "Restoran", "Park"))
        self.sinema, self.restoran, self.park = self.poll.options.all()
        self.url = reverse("poll_vote", args=[self.poll.pk])

    def browser(self):
        """A client that already has a voter cookie (as after visiting any page)."""
        client = Client()
        client.get(reverse("poll_list"))
        return client

    def vote(self, client, option, **extra):
        return client.post(self.url, {"option_id": option.pk}, **{**JSON, **extra})


class VoterCookieTests(VoteTestCase):
    def test_cookie_is_set_with_safe_attributes(self):
        response = self.client.get(reverse("poll_list"))
        cookie = response.cookies[VOTER_COOKIE_NAME]
        uuid.UUID(cookie.value, version=4)
        self.assertTrue(cookie["httponly"])
        self.assertEqual(cookie["samesite"], "Lax")
        self.assertEqual(cookie["max-age"], 60 * 60 * 24 * 365)

    def test_existing_cookie_is_kept(self):
        client = self.browser()
        response = client.get(reverse("poll_list"))
        self.assertNotIn(VOTER_COOKIE_NAME, response.cookies)

    def test_malformed_cookie_is_replaced(self):
        self.client.cookies[VOTER_COOKIE_NAME] = "hacked' OR 1=1"
        response = self.client.get(reverse("poll_list"))
        uuid.UUID(response.cookies[VOTER_COOKIE_NAME].value, version=4)


class VoteApiTests(VoteTestCase):
    def test_visitor_can_vote(self):
        client = self.browser()
        response = self.vote(client, self.sinema)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["ok"], True)
        self.assertEqual(data["total_votes"], 1)
        self.assertEqual(data["voted_option_id"], self.sinema.pk)
        self.assertEqual(
            data["results"],
            [
                {"id": self.sinema.pk, "text": "Sinema", "votes": 1, "percent": 100},
                {"id": self.restoran.pk, "text": "Restoran", "votes": 0, "percent": 0},
                {"id": self.park.pk, "text": "Park", "votes": 0, "percent": 0},
            ],
        )
        vote = Vote.objects.get()
        self.assertIsNone(vote.user)
        self.assertEqual(vote.voter_token, client.cookies[VOTER_COOKIE_NAME].value)

    def test_visitor_second_vote_with_same_cookie_is_409(self):
        client = self.browser()
        self.vote(client, self.sinema)
        response = self.vote(client, self.restoran)
        self.assertEqual(response.status_code, 409)
        data = response.json()
        self.assertEqual(data["error"], "already_voted")
        self.assertEqual(data["voted_option_id"], self.sinema.pk)
        self.assertEqual(data["total_votes"], 1)
        self.assertEqual(len(data["results"]), 3)
        self.assertEqual(Vote.objects.count(), 1)

    def test_different_browsers_can_each_vote(self):
        self.vote(self.browser(), self.sinema)
        self.vote(self.browser(), self.restoran)
        self.assertEqual(Vote.objects.count(), 2)

    def test_member_can_vote_and_second_vote_is_409(self):
        client = self.browser()
        client.force_login(self.author)  # authors may vote on their own poll
        self.assertEqual(self.vote(client, self.park).status_code, 200)
        vote = Vote.objects.get()
        self.assertEqual(vote.user, self.author)
        self.assertIsNotNone(vote.voter_token)
        self.assertEqual(self.vote(client, self.sinema).status_code, 409)

    def test_member_cannot_vote_again_from_another_browser(self):
        first = self.browser()
        first.force_login(self.author)
        self.vote(first, self.park)
        second = self.browser()
        second.force_login(self.author)
        response = self.vote(second, self.sinema)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["voted_option_id"], self.park.pk)

    def test_visitor_who_voted_cannot_vote_again_after_logging_in(self):
        client = self.browser()
        self.vote(client, self.sinema)
        client.post(reverse("login"), {"email": "ayse@example.com", "password": PASSWORD})
        response = self.vote(client, self.restoran)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(Vote.objects.count(), 1)

    def test_option_from_another_poll_is_400(self):
        other = make_poll(self.author, "Başka bir anket?", options=("A1", "B2"))
        response = self.vote(self.browser(), other.options.first())
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {"ok": False, "error": "invalid_option"})
        self.assertFalse(Vote.objects.exists())

    def test_missing_or_garbage_option_is_400(self):
        client = self.browser()
        for data in ({}, {"option_id": "abc"}, {"option_id": "999999"}):
            with self.subTest(data=data):
                self.assertEqual(client.post(self.url, data, **JSON).status_code, 400)

    def test_get_is_not_allowed(self):
        self.assertEqual(self.client.get(self.url).status_code, 405)

    def test_unknown_poll_is_404(self):
        response = self.browser().post(reverse("poll_vote", args=[999]), {"option_id": 1}, **JSON)
        self.assertEqual(response.status_code, 404)

    def test_json_never_contains_email(self):
        client = self.browser()
        client.force_login(self.author)
        self.assertNotIn(b"ayse@example.com", self.vote(client, self.sinema).content)

    def test_csrf_is_enforced(self):
        client = Client(enforce_csrf_checks=True)
        client.get(reverse("poll_list"))
        response = client.post(self.url, {"option_id": self.sinema.pk}, **JSON)
        self.assertEqual(response.status_code, 403)

    def test_race_is_caught_by_database_constraint(self):
        token = str(uuid.uuid4())
        Vote.objects.create(poll=self.poll, option=self.sinema, voter_token=token)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Vote.objects.create(poll=self.poll, option=self.park, voter_token=token)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Vote.objects.create(poll=self.poll, option=self.park)  # neither user nor token


class VoteWithoutJavaScriptTests(VoteTestCase):
    def test_form_post_redirects_to_detail_with_message(self):
        client = self.browser()
        response = client.post(self.url, {"option_id": self.sinema.pk}, follow=True)
        self.assertRedirects(response, self.poll.get_absolute_url())
        self.assertContains(response, "Oyun kaydedildi")
        self.assertContains(response, "Senin oyun ✓")

    def test_second_form_post_shows_already_voted(self):
        client = self.browser()
        client.post(self.url, {"option_id": self.sinema.pk})
        response = client.post(self.url, {"option_id": self.park.pk}, follow=True)
        self.assertContains(response, "Bu ankete zaten oy vermişsin.")
        self.assertEqual(Vote.objects.count(), 1)


class ResultsViewTests(VoteTestCase):
    def test_percent_rounding(self):
        self.assertEqual(percent(0, 0), 0)
        self.assertEqual(percent(1, 3), 33)
        self.assertEqual(percent(2, 3), 67)
        self.assertEqual(percent(1, 8), 13)  # 12.5 rounds half up

    def test_percentages_in_response(self):
        self.vote(self.browser(), self.sinema)
        self.vote(self.browser(), self.sinema)
        data = self.vote(self.browser(), self.restoran).json()
        self.assertEqual([r["percent"] for r in data["results"]], [67, 33, 0])
        self.assertEqual(data["total_votes"], 3)

    def test_feed_shows_vote_buttons_before_and_results_after_voting(self):
        client = self.browser()
        before = client.get(reverse("poll_list"))
        self.assertContains(before, 'name="option_id"')
        self.assertNotContains(before, "Senin oyun")
        self.vote(client, self.restoran)
        after = client.get(reverse("poll_list"))
        self.assertNotContains(after, "Oy ver, sonuçları gör")  # results view, not the vote form
        self.assertContains(after, "Oyumu değiştir")
        self.assertContains(after, "Senin oyun ✓")
        self.assertContains(after, "%100 · 1 oy")
        self.assertContains(after, "is-winner")

    def test_detail_keeps_results_after_reload(self):
        client = self.browser()
        self.vote(client, self.park)
        response = client.get(self.poll.get_absolute_url())
        self.assertContains(response, "Senin oyun ✓")
        self.assertNotContains(response, "Oy ver, sonuçları gör")

    def test_total_votes_visible_before_voting(self):
        self.vote(self.browser(), self.sinema)
        self.vote(self.browser(), self.park)
        response = self.browser().get(reverse("poll_list"))
        self.assertContains(response, '<span data-total-votes>2</span> oy')

    def test_other_member_on_shared_browser_sees_results_without_mine_badge(self):
        client = self.browser()
        client.force_login(self.author)
        self.vote(client, self.sinema)
        other = User.objects.create_user("mehmet", "mehmet@example.com", PASSWORD)
        client.force_login(other)
        response = client.get(self.poll.get_absolute_url())
        self.assertNotContains(response, 'name="option_id"')
        self.assertNotContains(response, "Senin oyun")
        self.assertEqual(self.vote(client, self.park).status_code, 409)

    def test_feed_query_count_is_constant_with_votes(self):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        client = self.browser()
        self.vote(client, self.sinema)
        with CaptureQueriesContext(connection) as few:
            client.get(reverse("poll_list"))
        for i in range(6):
            poll = make_poll(self.author, f"Ek anket sorusu {i}")
            client.post(reverse("poll_vote", args=[poll.pk]), {"option_id": poll.options.first().pk}, **JSON)
        with CaptureQueriesContext(connection) as many:
            client.get(reverse("poll_list"))
        self.assertEqual(len(few), len(many))
