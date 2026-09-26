from datetime import timedelta

from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from polls.models import Poll, Vote

from .test_polls import PASSWORD, make_poll

JSON = {"HTTP_ACCEPT": "application/json"}


class BaseCase(TestCase):
    def setUp(self):
        self.author = User.objects.create_user("ayse", "ayse@example.com", PASSWORD)
        self.poll = make_poll(self.author, options=("Sinema", "Restoran"))
        self.sinema, self.restoran = self.poll.options.all()
        self.url = reverse("poll_vote", args=[self.poll.pk])

    def browser(self):
        client = Client()
        client.get(reverse("poll_list"))
        return client


class ChangeVoteTests(BaseCase):
    def test_visitor_can_change_vote(self):
        c = self.browser()
        c.post(self.url, {"option_id": self.sinema.pk}, **JSON)
        r = c.post(self.url, {"option_id": self.restoran.pk, "change": "1"}, **JSON)
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertTrue(data["ok"])
        self.assertTrue(data["can_change"])
        self.assertEqual(data["voted_option_id"], self.restoran.pk)
        self.assertEqual([x["votes"] for x in data["results"]], [0, 1])
        self.assertEqual(Vote.objects.count(), 1)

    def test_without_change_flag_still_409(self):
        c = self.browser()
        c.post(self.url, {"option_id": self.sinema.pk}, **JSON)
        r = c.post(self.url, {"option_id": self.restoran.pk}, **JSON)
        self.assertEqual(r.status_code, 409)
        self.assertTrue(r.json()["can_change"])
        self.assertEqual(Vote.objects.get().option, self.sinema)

    def test_change_without_previous_vote_just_votes(self):
        r = self.browser().post(self.url, {"option_id": self.sinema.pk, "change": "1"}, **JSON)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(Vote.objects.count(), 1)

    def test_member_changes_from_another_browser(self):
        first = self.browser(); first.force_login(self.author)
        first.post(self.url, {"option_id": self.sinema.pk}, **JSON)
        second = self.browser(); second.force_login(self.author)
        r = second.post(self.url, {"option_id": self.restoran.pk, "change": "1"}, **JSON)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(Vote.objects.get().option, self.restoran)

    def test_cannot_change_someone_elses_vote_on_shared_browser(self):
        c = self.browser(); c.force_login(self.author)
        c.post(self.url, {"option_id": self.sinema.pk}, **JSON)
        other = User.objects.create_user("mehmet", "m@example.com", PASSWORD)
        c.force_login(other)
        r = c.post(self.url, {"option_id": self.restoran.pk, "change": "1"}, **JSON)
        self.assertEqual(r.status_code, 409)
        self.assertFalse(r.json()["can_change"])
        self.assertEqual(Vote.objects.get().option, self.sinema)

    def test_change_block_rendered_after_voting(self):
        c = self.browser()
        c.post(self.url, {"option_id": self.sinema.pk}, **JSON)
        page = c.get(self.poll.get_absolute_url())
        self.assertContains(page, "Oyumu değiştir")
        self.assertContains(page, 'name="change" value="1"')

    def test_no_js_change_redirects_with_message(self):
        c = self.browser()
        c.post(self.url, {"option_id": self.sinema.pk})
        r = c.post(self.url, {"option_id": self.restoran.pk, "change": "1"}, follow=True)
        self.assertContains(r, "Oyun güncellendi")


class ClosingPollTests(BaseCase):
    def close(self):
        Poll.objects.filter(pk=self.poll.pk).update(closes_at=timezone.now() - timedelta(minutes=1))

    def test_create_with_duration_sets_closes_at(self):
        self.client.force_login(self.author)
        self.client.post(reverse("poll_create"), {"question": "Süreli bir soru mu?", "options": ["A1", "B2"], "duration": "1g"})
        poll = Poll.objects.latest("pk")
        self.assertAlmostEqual((poll.closes_at - timezone.now()).total_seconds(), 86400, delta=60)
        self.assertFalse(poll.is_closed)

    def test_default_duration_is_unlimited(self):
        self.client.force_login(self.author)
        self.client.post(reverse("poll_create"), {"question": "Süresiz bir soru mu?", "options": ["A1", "B2"]})
        self.assertIsNone(Poll.objects.latest("pk").closes_at)

    def test_invalid_duration_rejected(self):
        self.client.force_login(self.author)
        r = self.client.post(reverse("poll_create"), {"question": "Süreli bir soru mu?", "options": ["A1", "B2"], "duration": "99y"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(Poll.objects.count(), 1)

    def test_closed_poll_rejects_votes_and_changes(self):
        c = self.browser()
        c.post(self.url, {"option_id": self.sinema.pk}, **JSON)
        self.close()
        r = c.post(self.url, {"option_id": self.restoran.pk, "change": "1"}, **JSON)
        self.assertEqual(r.status_code, 403)
        self.assertEqual(r.json()["error"], "poll_closed")
        self.assertTrue(r.json()["closed"])
        r = self.browser().post(self.url, {"option_id": self.restoran.pk}, **JSON)
        self.assertEqual(r.status_code, 403)
        self.assertEqual(Vote.objects.count(), 1)

    def test_closed_poll_shows_results_to_everyone(self):
        self.browser().post(self.url, {"option_id": self.sinema.pk}, **JSON)
        self.close()
        page = self.browser().get(self.poll.get_absolute_url())
        self.assertContains(page, "Oylama kapandı")
        self.assertContains(page, "%100 · 1 oy")
        self.assertNotContains(page, 'name="option_id"')
        self.assertNotContains(page, "Oyumu değiştir")

    def test_open_poll_shows_time_left(self):
        Poll.objects.filter(pk=self.poll.pk).update(closes_at=timezone.now() + timedelta(hours=2, minutes=5))
        self.assertContains(self.client.get(reverse("poll_list")), "2\xa0saat kaldı")
