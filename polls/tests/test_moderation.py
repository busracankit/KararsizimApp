from django.contrib.admin.sites import site
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from accounts.models import User
from polls.models import REPORT_AUTO_HIDE_THRESHOLD, Comment, Poll, Report, Vote

from .test_polls import PASSWORD, make_poll

JSON = {"HTTP_ACCEPT": "application/json"}


class ReportTests(TestCase):
    def setUp(self):
        self.author = User.objects.create_user("ayse", "ayse@example.com", PASSWORD)
        self.poll = make_poll(self.author, "Şikayet edilecek soru?")
        self.url = reverse("poll_report", args=[self.poll.pk])

    def browser(self):
        c = Client(); c.get("/")
        return c

    def test_visitor_can_report_once(self):
        c = self.browser()
        self.assertContains(c.get(self.url), "Neden şikayet ediyorsun?")
        r = c.post(self.url, {"reason": "spam", "note": "reklam"}, follow=True)
        self.assertContains(r, "şikayetin moderatörlere iletildi")
        report = Report.objects.get()
        self.assertEqual((report.reason, report.note, report.reporter), ("spam", "reklam", None))
        r = c.post(self.url, {"reason": "spam"}, follow=True)
        self.assertContains(r, "zaten şikayet ettin")
        self.assertEqual(Report.objects.count(), 1)

    def test_member_cannot_report_twice_from_different_browsers(self):
        other = User.objects.create_user("mehmet", "m@example.com", PASSWORD)
        a = self.browser(); a.force_login(other)
        a.post(self.url, {"reason": "hakaret"})
        b = self.browser(); b.force_login(other)
        b.post(self.url, {"reason": "hakaret"})
        self.assertEqual(Report.objects.count(), 1)

    def test_reason_required(self):
        r = self.browser().post(self.url, {"reason": ""})
        self.assertContains(r, "Bir sebep seç.")
        self.assertFalse(Report.objects.exists())

    def test_author_cannot_report_own_poll(self):
        c = self.browser(); c.force_login(self.author)
        r = c.post(self.url, {"reason": "spam"}, follow=True)
        self.assertContains(r, "Kendi anketini şikayet edemezsin")
        self.assertNotContains(c.get(self.poll.get_absolute_url()), "Şikayet et")

    def test_auto_hide_after_threshold(self):
        for _ in range(REPORT_AUTO_HIDE_THRESHOLD):
            self.browser().post(self.url, {"reason": "spam"})
        self.poll.refresh_from_db()
        self.assertTrue(self.poll.is_hidden)

    def test_hidden_poll_is_invisible_to_public(self):
        Poll.objects.filter(pk=self.poll.pk).update(is_hidden=True)
        self.assertNotContains(self.client.get("/"), "Şikayet edilecek soru?")
        self.assertNotContains(self.client.get("/", {"q": "şikayet"}), "Şikayet edilecek soru?")
        self.assertNotContains(self.client.get(reverse("user_profile", args=["ayse"])), "Şikayet edilecek soru?")
        self.assertEqual(self.client.get(self.poll.get_absolute_url()).status_code, 404)
        c = self.browser()
        r = c.post(reverse("poll_vote", args=[self.poll.pk]), {"option_id": self.poll.options.first().pk}, **JSON)
        self.assertEqual(r.status_code, 404)
        self.assertFalse(Vote.objects.exists())

    def test_author_and_staff_still_see_hidden_poll(self):
        Poll.objects.filter(pk=self.poll.pk).update(is_hidden=True)
        self.client.force_login(self.author)
        self.assertContains(self.client.get(self.poll.get_absolute_url()), "şikayetler nedeniyle gizlendi")
        staff = User.objects.create_user("mod", "mod@example.com", PASSWORD, is_staff=True)
        self.client.force_login(staff)
        self.assertEqual(self.client.get(self.poll.get_absolute_url()).status_code, 200)

    @override_settings(RATE_LIMITS={"report": (1, 3600, "ip")})
    def test_reports_rate_limited(self):
        second = make_poll(self.author, "İkinci soru burada?")
        self.browser().post(self.url, {"reason": "spam"})
        r = self.browser().post(reverse("poll_report", args=[second.pk]), {"reason": "spam"}, follow=True)
        self.assertContains(r, "çok fazla şikayet")
        self.assertEqual(Report.objects.count(), 1)


class CommentTests(TestCase):
    def setUp(self):
        self.author = User.objects.create_user("ayse", "ayse@example.com", PASSWORD)
        self.member = User.objects.create_user("mehmet", "mehmet@example.com", PASSWORD)
        self.poll = make_poll(self.author)
        self.url = reverse("comment_create", args=[self.poll.pk])

    def test_visitor_cannot_comment(self):
        r = self.client.post(self.url, {"text": "Merhaba"})
        self.assertRedirects(r, f"{reverse('login')}?next={self.url}", fetch_redirect_response=False)
        self.assertFalse(Comment.objects.exists())
        self.assertContains(self.client.get(self.poll.get_absolute_url()), "Giriş yap</a> ya da")

    def test_member_comments(self):
        self.client.force_login(self.member)
        r = self.client.post(self.url, {"text": "Bence sinema <b>kesin</b>"})
        comment = Comment.objects.get()
        self.assertRedirects(r, f"{self.poll.get_absolute_url()}#yorum-{comment.pk}", fetch_redirect_response=False)
        page = self.client.get(self.poll.get_absolute_url())
        self.assertContains(page, "Bence sinema &lt;b&gt;kesin&lt;/b&gt;")
        self.assertContains(page, "@mehmet")
        self.assertNotContains(page, "mehmet@example.com")

    def test_empty_and_too_long_comments_rejected(self):
        self.client.force_login(self.member)
        self.assertContains(self.client.post(self.url, {"text": "   "}, follow=True), "Boş yorum gönderemezsin.")
        self.assertContains(self.client.post(self.url, {"text": "x" * 501}, follow=True), "en fazla 500 karakter")
        self.assertFalse(Comment.objects.exists())

    def test_comment_count_on_card(self):
        Comment.objects.create(poll=self.poll, author=self.member, text="bir")
        Comment.objects.create(poll=self.poll, author=self.member, text="gizli", is_hidden=True)
        self.assertContains(self.client.get("/"), "💬 1</a>")

    def test_hidden_comment_not_shown(self):
        Comment.objects.create(poll=self.poll, author=self.member, text="Gizli yorum metni", is_hidden=True)
        self.assertNotContains(self.client.get(self.poll.get_absolute_url()), "Gizli yorum metni")

    def test_delete_permissions(self):
        comment = Comment.objects.create(poll=self.poll, author=self.member, text="sil beni")
        url = reverse("comment_delete", args=[comment.pk])
        stranger = User.objects.create_user("zeynep", "z@example.com", PASSWORD)
        self.client.force_login(stranger)
        self.assertEqual(self.client.post(url).status_code, 404)
        self.client.force_login(self.author)  # poll owner may remove comments on their poll
        self.client.post(url)
        self.assertFalse(Comment.objects.exists())
        comment = Comment.objects.create(poll=self.poll, author=self.member, text="kendi yorumum")
        self.client.force_login(self.member)
        self.assertEqual(self.client.get(reverse("comment_delete", args=[comment.pk])).status_code, 405)
        self.client.post(reverse("comment_delete", args=[comment.pk]))
        self.assertFalse(Comment.objects.exists())

    @override_settings(RATE_LIMITS={"comment": (2, 600, "user")})
    def test_comments_rate_limited(self):
        self.client.force_login(self.member)
        for i in range(3):
            self.client.post(self.url, {"text": f"yorum {i}"})
        self.assertEqual(Comment.objects.count(), 2)

    def test_counts_are_independent(self):
        from polls.services import polls_with_counts
        for i in range(3):
            Vote.objects.create(poll=self.poll, option=self.poll.options.first(), voter_token=f"t{i}")
        for i in range(2):
            Comment.objects.create(poll=self.poll, author=self.member, text=f"y{i}")
        poll = polls_with_counts().get(pk=self.poll.pk)
        self.assertEqual((poll.total_votes, poll.comment_count), (3, 2))


class AdminTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser("admin", "admin@example.com", PASSWORD)
        self.client.force_login(self.admin)
        self.poll = make_poll(self.admin)

    def test_admin_pages_load(self):
        for model in ("poll", "report", "comment", "vote"):
            with self.subTest(model=model):
                self.assertEqual(self.client.get(f"/admin/polls/{model}/").status_code, 200)
        self.assertEqual(self.client.get(f"/admin/polls/poll/{self.poll.pk}/change/").status_code, 200)

    def test_unhide_action_resolves_reports(self):
        Poll.objects.filter(pk=self.poll.pk).update(is_hidden=True)
        Report.objects.create(poll=self.poll, voter_token="t", reason="spam")
        self.client.post("/admin/polls/poll/", {"action": "unhide_polls", "_selected_action": [self.poll.pk]})
        self.poll.refresh_from_db()
        self.assertFalse(self.poll.is_hidden)
        self.assertTrue(Report.objects.get().resolved)
