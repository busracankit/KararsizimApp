from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from polls.models import Poll
from polls.views import search_variants

from .test_polls import PASSWORD, make_poll


class CategoryTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("ayse", "ayse@example.com", PASSWORD)

    def test_create_with_category(self):
        self.client.force_login(self.user)
        self.client.post(reverse("poll_create"), {"question": "Hangi pizzayı alsam?", "options": ["Margarita", "Karışık"], "category": "yemek"})
        self.assertEqual(Poll.objects.get().category, "yemek")

    def test_default_category_is_other(self):
        self.client.force_login(self.user)
        self.client.post(reverse("poll_create"), {"question": "Hangi pizzayı alsam?", "options": ["Margarita", "Karışık"]})
        self.assertEqual(Poll.objects.get().category, "diger")

    def test_invalid_category_rejected(self):
        self.client.force_login(self.user)
        r = self.client.post(reverse("poll_create"), {"question": "Hangi pizzayı alsam?", "options": ["A1", "B2"], "category": "hack"})
        self.assertContains(r, "Geçersiz kategori.")
        self.assertFalse(Poll.objects.exists())

    def test_filter_by_category(self):
        food = make_poll(self.user, "Yemek sorusu burada?")
        Poll.objects.filter(pk=food.pk).update(category="yemek")
        make_poll(self.user, "Diğer soru burada?")
        r = self.client.get(reverse("poll_list"), {"kategori": "yemek"})
        self.assertContains(r, "Yemek sorusu burada?")
        self.assertNotContains(r, "Diğer soru burada?")
        self.assertContains(r, 'aria-current="page"><span aria-hidden="true">🍕</span> Yemek &amp; içecek')

    def test_unknown_category_shows_all(self):
        make_poll(self.user, "Diğer soru burada?")
        self.assertContains(self.client.get(reverse("poll_list"), {"kategori": "yok"}), "Diğer soru burada?")

    def test_card_shows_category_tag(self):
        make_poll(self.user)
        self.assertContains(self.client.get(reverse("poll_list")), "?kategori=diger")


class SearchTests(TestCase):
    def setUp(self):
        user = User.objects.create_user("ayse", "ayse@example.com", PASSWORD)
        make_poll(user, "Tatil için nereye gitsem?", options=("Antalya", "Bodrum"))
        make_poll(user, "Akşam ne yesem?", options=("Pizza", "Mantı"))

    def get(self, **params):
        return self.client.get(reverse("poll_list"), params)

    def test_search_question(self):
        r = self.get(q="tatil")
        self.assertContains(r, "Tatil için nereye gitsem?")
        self.assertNotContains(r, "Akşam ne yesem?")

    def test_search_option_text_without_duplicates(self):
        r = self.get(q="a")  # matches many options of the same poll
        self.assertEqual(r.context["page"].paginator.count, 2)

    def test_search_option(self):
        r = self.get(q="mantı")
        self.assertContains(r, "Akşam ne yesem?")
        self.assertNotContains(r, "Tatil için")

    def test_no_results(self):
        r = self.get(q="uzay gemisi")
        self.assertContains(r, "için henüz anket yok")
        self.assertContains(r, "Filtreleri temizle")

    def test_search_keeps_other_filters_in_links(self):
        r = self.get(q="tatil", kategori="seyahat", sirala="populer")
        self.assertContains(r, 'name="kategori" value="seyahat"')
        self.assertContains(r, "?q=tatil&amp;kategori=seyahat")

    def test_query_is_escaped(self):
        r = self.get(q="<script>alert(1)</script>")
        self.assertNotContains(r, "<script>alert(1)</script>")

    def test_turkish_variants(self):
        self.assertIn("İSTANBUL", search_variants("istanbul"))
        self.assertIn("IŞIK", search_variants("ışık"))

    def test_counts_not_inflated_by_search_join(self):
        from polls.models import Vote
        poll = Poll.objects.get(question__startswith="Tatil")
        Vote.objects.create(poll=poll, option=poll.options.first(), voter_token="t1")
        r = self.get(q="a")
        polls = {p.question: p.total_votes for p in r.context["page"].object_list}
        self.assertEqual(polls["Tatil için nereye gitsem?"], 1)
