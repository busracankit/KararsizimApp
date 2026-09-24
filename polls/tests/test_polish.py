from datetime import timedelta

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from polls.models import Option, Poll, Vote

from .test_polls import PASSWORD, make_poll

JSON = {"HTTP_ACCEPT": "application/json"}


class PollDeleteTests(TestCase):
    def setUp(self):
        self.author = User.objects.create_user("ayse", "ayse@example.com", PASSWORD)
        self.other = User.objects.create_user("mehmet", "mehmet@example.com", PASSWORD)
        self.poll = make_poll(self.author)
        self.url = reverse("poll_delete", args=[self.poll.pk])
        Vote.objects.create(poll=self.poll, option=self.poll.options.first(), voter_token="t-1")

    def test_visitor_is_sent_to_login(self):
        response = self.client.get(self.url)
        self.assertRedirects(response, f"{reverse('login')}?next={self.url}")

    def test_author_sees_confirmation_and_get_does_not_delete(self):
        self.client.force_login(self.author)
        response = self.client.get(self.url)
        self.assertContains(response, "Anketi silmek istiyor musun?")
        self.assertContains(response, "1 oy")
        self.assertTrue(Poll.objects.filter(pk=self.poll.pk).exists())

    def test_author_can_delete_with_post(self):
        self.client.force_login(self.author)
        response = self.client.post(self.url, follow=True)
        self.assertRedirects(response, reverse("user_profile", args=["ayse"]))
        self.assertContains(response, "Anketin silindi.")
        self.assertFalse(Poll.objects.exists())
        self.assertFalse(Option.objects.exists())
        self.assertFalse(Vote.objects.exists())

    def test_other_user_gets_404_and_nothing_is_deleted(self):
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(self.url).status_code, 404)
        self.assertEqual(self.client.post(self.url).status_code, 404)
        self.assertTrue(Poll.objects.filter(pk=self.poll.pk).exists())

    def test_delete_link_only_for_author(self):
        detail = self.poll.get_absolute_url()
        self.assertNotContains(self.client.get(detail), self.url)
        self.client.force_login(self.other)
        self.assertNotContains(self.client.get(detail), self.url)
        self.client.force_login(self.author)
        self.assertContains(self.client.get(detail), self.url)


class UserProfileTests(TestCase):
    def setUp(self):
        self.ayse = User.objects.create_user("ayse", "ayse@example.com", PASSWORD)
        self.mehmet = User.objects.create_user("mehmet", "mehmet@example.com", PASSWORD)
        make_poll(self.ayse, "Ayşe'nin sorusu burada?")
        make_poll(self.mehmet, "Mehmet'in sorusu burada?")

    def test_profile_lists_only_that_users_polls_without_email(self):
        response = self.client.get(reverse("user_profile", args=["ayse"]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "@ayse")
        self.assertContains(response, "Ayşe&#x27;nin sorusu burada?")
        self.assertNotContains(response, "Mehmet&#x27;in sorusu")
        self.assertContains(response, "1 anket")
        self.assertNotContains(response, "ayse@example.com")

    def test_username_lookup_is_case_insensitive(self):
        self.assertEqual(self.client.get(reverse("user_profile", args=["AYSE"])).status_code, 200)

    def test_unknown_or_inactive_user_is_404(self):
        self.assertEqual(self.client.get(reverse("user_profile", args=["yok"])).status_code, 404)
        self.mehmet.is_active = False
        self.mehmet.save()
        self.assertEqual(self.client.get(reverse("user_profile", args=["mehmet"])).status_code, 404)

    def test_author_names_link_to_profiles(self):
        response = self.client.get(reverse("poll_list"))
        self.assertContains(response, reverse("user_profile", args=["ayse"]))

    def test_empty_profile(self):
        User.objects.create_user("zeynep", "z@example.com", PASSWORD)
        self.assertContains(self.client.get(reverse("user_profile", args=["zeynep"])), "henüz anket açmamış")


class FeedSortTests(TestCase):
    def setUp(self):
        user = User.objects.create_user("ayse", "ayse@example.com", PASSWORD)
        now = timezone.now()
        self.old_popular = make_poll(user, "Eski ama popüler soru", created_at=now - timedelta(days=3))
        self.new_quiet = make_poll(user, "Yeni ama sessiz soru", created_at=now)
        for i in range(3):
            Vote.objects.create(poll=self.old_popular, option=self.old_popular.options.first(), voter_token=f"t{i}")

    def order(self, **params):
        content = self.client.get(reverse("poll_list"), params).content.decode()
        return content.index("Eski ama popüler") < content.index("Yeni ama sessiz")

    def test_default_is_newest_first(self):
        self.assertFalse(self.order())

    def test_popular_sort(self):
        self.assertTrue(self.order(sirala="populer"))
        response = self.client.get(reverse("poll_list"), {"sirala": "populer"})
        self.assertContains(response, 'aria-current="page">🔥 En çok oylanan')

    def test_unknown_sort_falls_back_to_newest(self):
        self.assertFalse(self.order(sirala="hacked"))

    def test_pagination_keeps_sort(self):
        user = User.objects.get(username="ayse")
        for i in range(10):
            make_poll(user, f"Doldurma anketi {i:02d}")
        response = self.client.get(reverse("poll_list"), {"sirala": "populer"})
        self.assertContains(response, "?sirala=populer&amp;sayfa=2")


class MetaAndErrorPageTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("ayse", "ayse@example.com", PASSWORD)
        self.poll = make_poll(self.user, "Kahve mi çay mı?", options=("Kahve", "Çay"))

    def test_detail_has_open_graph_tags_with_question(self):
        response = self.client.get(self.poll.get_absolute_url())
        self.assertContains(response, '<meta property="og:title" content="Kahve mi çay mı?">')
        self.assertContains(response, "Kahve / Çay")
        self.assertContains(response, f'<meta property="og:url" content="http://testserver{self.poll.get_absolute_url()}">')
        self.assertContains(response, "<title>Kahve mi çay mı? — Kararsızım</title>")

    def test_skip_link_present(self):
        self.assertContains(self.client.get(reverse("poll_list")), 'class="skip-link" href="#main"')

    @override_settings(DEBUG=False)
    def test_custom_404_page(self):
        response = self.client.get("/boyle-bir-sayfa-yok/")
        self.assertEqual(response.status_code, 404)
        self.assertContains(response, "Burada bir şey yok", status_code=404)

    def test_500_template_renders_without_request_context(self):
        from django.template.loader import render_to_string

        html = render_to_string("500.html")
        self.assertIn("Bir şeyler ters gitti", html)
