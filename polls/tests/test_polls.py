from datetime import timedelta

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from polls.models import Option, Poll

PASSWORD = "guclu-parola-123"


def make_poll(author, question="Sinema mı restoran mı?", options=("Sinema", "Restoran"), created_at=None):
    poll = Poll.objects.create(author=author, question=question)
    for order, text in enumerate(options):
        Option.objects.create(poll=poll, text=text, order=order)
    if created_at:
        Poll.objects.filter(pk=poll.pk).update(created_at=created_at)
        poll.refresh_from_db()
    return poll


class PollCreateTests(TestCase):
    url = reverse("poll_create")

    def setUp(self):
        self.user = User.objects.create_user("ayse", "ayse@example.com", PASSWORD)

    def post(self, question="Bugün sinemaya mı gitsem, restorana mı?", options=("Sinema", "Restoran")):
        return self.client.post(self.url, {"question": question, "options": list(options)})

    def test_visitor_is_redirected_to_login_with_next(self):
        response = self.client.get(self.url)
        self.assertRedirects(response, f"{reverse('login')}?next={self.url}")

    def test_visitor_cannot_create_by_post(self):
        self.post()
        self.assertFalse(Poll.objects.exists())

    def test_member_sees_form_with_two_option_inputs(self):
        self.client.force_login(self.user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content.decode().count('name="options"'), 3)  # 2 inputs + 1 in <template>

    def test_valid_poll_is_created_with_ordered_options(self):
        self.client.force_login(self.user)
        response = self.post(options=["  Sinema ", "Restoran", "Evde film"])
        poll = Poll.objects.get()
        self.assertRedirects(response, poll.get_absolute_url())
        self.assertEqual(poll.author, self.user)
        self.assertEqual(poll.question, "Bugün sinemaya mı gitsem, restorana mı?")
        self.assertEqual(list(poll.options.values_list("text", "order")), [("Sinema", 0), ("Restoran", 1), ("Evde film", 2)])

    def test_five_options_are_allowed(self):
        self.client.force_login(self.user)
        self.post(options=["A1", "B2", "C3", "D4", "E5"])
        self.assertEqual(Poll.objects.get().options.count(), 5)

    def test_one_option_is_rejected(self):
        self.client.force_login(self.user)
        response = self.post(options=["Sinema"])
        self.assertContains(response, "En az 2 seçenek yazmalısın.")
        self.assertFalse(Poll.objects.exists())

    def test_six_options_are_rejected(self):
        self.client.force_login(self.user)
        response = self.post(options=["A1", "B2", "C3", "D4", "E5", "F6"])
        self.assertContains(response, "En fazla 5 seçenek ekleyebilirsin.")
        self.assertFalse(Poll.objects.exists())

    def test_blank_options_are_ignored_but_still_need_two(self):
        self.client.force_login(self.user)
        response = self.post(options=["Sinema", "   ", ""])
        self.assertContains(response, "En az 2 seçenek yazmalısın.")
        self.post(options=["Sinema", "", "Restoran"])
        self.assertEqual(list(Poll.objects.get().options.values_list("text", flat=True)), ["Sinema", "Restoran"])

    def test_duplicate_options_are_rejected_case_insensitive(self):
        self.client.force_login(self.user)
        for options in (["Sinema", "sinema "], ["Sinema", "SİNEMA"], ["Işık", "IŞIK"]):
            with self.subTest(options=options):
                response = self.post(options=options)
                self.assertContains(response, "Bu seçeneği zaten yazdın.")
        self.assertFalse(Poll.objects.exists())

    def test_turkish_dotless_i_is_a_different_letter(self):
        self.client.force_login(self.user)
        self.post(options=["Sınır", "Sinir"])
        self.assertEqual(Poll.objects.get().options.count(), 2)

    def test_too_long_option_is_rejected(self):
        self.client.force_login(self.user)
        response = self.post(options=["Sinema", "x" * 101])
        self.assertContains(response, "en fazla 100 karakter")
        self.assertFalse(Poll.objects.exists())

    def test_short_or_blank_question_is_rejected(self):
        self.client.force_login(self.user)
        for question, message in [("", "Soruyu yazmalısın."), ("Ne?", "en az 5 karakter")]:
            with self.subTest(question=question):
                response = self.post(question=question)
                self.assertContains(response, message)
        self.assertFalse(Poll.objects.exists())

    def test_invalid_form_keeps_typed_values(self):
        self.client.force_login(self.user)
        response = self.post(question="Ne?", options=["Sinema", "Restoran", "Park"])
        self.assertContains(response, 'value="Park"')


class PollListTests(TestCase):
    url = reverse("poll_list")

    def setUp(self):
        self.user = User.objects.create_user("ayse", "ayse@example.com", PASSWORD)

    def test_empty_state(self):
        response = self.client.get(self.url)
        self.assertContains(response, "Henüz anket yok")

    def test_newest_first(self):
        now = timezone.now()
        make_poll(self.user, "Eski anket sorusu", created_at=now - timedelta(days=2))
        make_poll(self.user, "Yeni anket sorusu", created_at=now)
        content = self.client.get(self.url).content.decode()
        self.assertLess(content.index("Yeni anket sorusu"), content.index("Eski anket sorusu"))
        self.assertNotContains(self.client.get(self.url), "Henüz anket yok")

    def test_card_shows_author_options_and_relative_time_but_not_email(self):
        make_poll(self.user, created_at=timezone.now() - timedelta(minutes=5))
        response = self.client.get(self.url)
        self.assertContains(response, "@ayse")
        self.assertContains(response, "Sinema")
        self.assertContains(response, "5\xa0dakika önce")
        self.assertNotContains(response, "ayse@example.com")

    def test_pagination_ten_per_page(self):
        now = timezone.now()
        for i in range(12):
            make_poll(self.user, f"Anket numarası {i:02d}", created_at=now - timedelta(minutes=i))
        first = self.client.get(self.url)
        self.assertEqual(len(first.context["page"].object_list), 10)
        self.assertContains(first, "Anket numarası 00")
        self.assertNotContains(first, "Anket numarası 10")
        second = self.client.get(self.url, {"sayfa": 2})
        self.assertEqual(len(second.context["page"].object_list), 2)
        self.assertContains(second, "Anket numarası 11")
        self.assertEqual(self.client.get(self.url, {"sayfa": "abc"}).status_code, 200)

    def test_query_count_does_not_grow_with_polls(self):
        for i in range(3):
            make_poll(self.user, f"Anket numarası {i}")
        with CaptureQueriesContext(connection) as few:
            self.client.get(self.url)
        for i in range(3, 10):
            make_poll(self.user, f"Anket numarası {i}")
        with CaptureQueriesContext(connection) as many:
            self.client.get(self.url)
        self.assertEqual(len(few), len(many))


class PollDetailTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("ayse", "ayse@example.com", PASSWORD)
        self.poll = make_poll(self.user)

    def test_detail_is_public(self):
        response = self.client.get(self.poll.get_absolute_url())
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.poll.question)
        self.assertContains(response, "@ayse")
        self.assertContains(response, "opt-2")
        self.assertNotContains(response, "ayse@example.com")

    def test_missing_poll_returns_404(self):
        self.assertEqual(self.client.get(reverse("poll_detail", args=[999])).status_code, 404)

    def test_create_redirects_to_detail_with_message(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("poll_create"), {"question": "Hangi kitabı okusam?", "options": ["Roman", "Deneme"]}, follow=True
        )
        self.assertContains(response, "Anketin yayında!")
        self.assertContains(response, "Hangi kitabı okusam?")
