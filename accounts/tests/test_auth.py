from django.contrib.auth import get_user
from django.test import TestCase
from django.urls import reverse

from accounts.models import User

PASSWORD = "guclu-parola-123"


class RegisterTests(TestCase):
    url = reverse("register")

    def post(self, **overrides):
        data = {"username": "ayse", "email": "Ayse@Example.com", "password1": PASSWORD, "password2": PASSWORD}
        data.update(overrides)
        return self.client.post(self.url, data)

    def test_register_page_renders(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Kayıt ol")

    def test_successful_registration_logs_in_and_redirects_home(self):
        response = self.post()
        self.assertRedirects(response, reverse("poll_list"))
        user = User.objects.get(username="ayse")
        self.assertEqual(user.email, "ayse@example.com")
        self.assertEqual(get_user(self.client).pk, user.pk)

    def test_duplicate_username_is_rejected_case_insensitive(self):
        User.objects.create_user("Ayse", "other@example.com", PASSWORD)
        response = self.post(username="aYSE")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Bu kullanıcı adı zaten alınmış.")
        self.assertEqual(User.objects.count(), 1)

    def test_duplicate_email_is_rejected_case_insensitive(self):
        User.objects.create_user("mehmet", "ayse@example.com", PASSWORD)
        response = self.post(email="AYSE@example.COM")
        self.assertContains(response, "Bu e-posta adresiyle zaten bir hesap var.")
        self.assertEqual(User.objects.count(), 1)

    def test_invalid_username_format_is_rejected(self):
        for bad in ["ab", "ayşe", "ayse kaya", "ayse!"]:
            with self.subTest(username=bad):
                response = self.post(username=bad)
                self.assertEqual(response.status_code, 200)
                self.assertFalse(User.objects.exists())

    def test_password_mismatch_is_rejected(self):
        response = self.post(password2="baska-parola-456")
        self.assertContains(response, "Parolalar eşleşmiyor.")
        self.assertFalse(User.objects.exists())

    def test_weak_password_is_rejected(self):
        response = self.post(password1="1234", password2="1234")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.exists())

    def test_register_honours_safe_next(self):
        response = self.client.post(
            self.url + "?next=/anket/yeni/",
            {"username": "ayse", "email": "a@example.com", "password1": PASSWORD, "password2": PASSWORD},
        )
        self.assertRedirects(response, "/anket/yeni/", fetch_redirect_response=False)


class LoginLogoutTests(TestCase):
    url = reverse("login")

    def setUp(self):
        self.user = User.objects.create_user("ayse", "ayse@example.com", PASSWORD)

    def test_login_with_email(self):
        response = self.client.post(self.url, {"email": "ayse@example.com", "password": PASSWORD})
        self.assertRedirects(response, reverse("poll_list"))
        self.assertEqual(get_user(self.client).pk, self.user.pk)

    def test_login_email_is_case_insensitive(self):
        self.client.post(self.url, {"email": "AYSE@Example.com", "password": PASSWORD})
        self.assertTrue(get_user(self.client).is_authenticated)

    def test_wrong_password_is_rejected(self):
        response = self.client.post(self.url, {"email": "ayse@example.com", "password": "yanlis-parola"})
        self.assertContains(response, "E-posta veya parola hatalı.")
        self.assertFalse(get_user(self.client).is_authenticated)

    def test_unknown_email_is_rejected_with_same_message(self):
        response = self.client.post(self.url, {"email": "yok@example.com", "password": PASSWORD})
        self.assertContains(response, "E-posta veya parola hatalı.")

    def test_inactive_user_cannot_log_in(self):
        self.user.is_active = False
        self.user.save()
        response = self.client.post(self.url, {"email": "ayse@example.com", "password": PASSWORD})
        self.assertContains(response, "E-posta veya parola hatalı.")

    def test_login_redirects_to_safe_next(self):
        response = self.client.post(
            self.url + "?next=/anket/yeni/", {"email": "ayse@example.com", "password": PASSWORD}
        )
        self.assertRedirects(response, "/anket/yeni/", fetch_redirect_response=False)

    def test_login_ignores_external_next(self):
        response = self.client.post(
            self.url + "?next=https://kotu-site.com/", {"email": "ayse@example.com", "password": PASSWORD}
        )
        self.assertRedirects(response, reverse("poll_list"))

    def test_logged_in_user_is_redirected_away_from_login_and_register(self):
        self.client.force_login(self.user)
        self.assertRedirects(self.client.get(self.url), reverse("poll_list"))
        self.assertRedirects(self.client.get(reverse("register")), reverse("poll_list"))

    def test_logout_requires_post(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(reverse("logout")).status_code, 405)
        self.assertTrue(get_user(self.client).is_authenticated)

    def test_logout(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse("logout"))
        self.assertRedirects(response, reverse("poll_list"))
        self.assertFalse(get_user(self.client).is_authenticated)

    def test_admin_login_with_username_still_works(self):
        User.objects.create_superuser("admin", "admin@example.com", PASSWORD)
        self.assertTrue(self.client.login(username="admin", password=PASSWORD))


class NavbarTests(TestCase):
    def test_visitor_sees_login_and_register(self):
        response = self.client.get(reverse("poll_list"))
        self.assertContains(response, reverse("login"))
        self.assertContains(response, reverse("register"))

    def test_member_sees_username_and_logout_but_never_email(self):
        user = User.objects.create_user("ayse", "ayse@example.com", PASSWORD)
        self.client.force_login(user)
        for url in [reverse("poll_list")]:
            response = self.client.get(url)
            self.assertContains(response, "@ayse")
            self.assertContains(response, reverse("logout"))
            self.assertNotContains(response, "ayse@example.com")

    def test_email_not_shown_after_registration(self):
        response = self.client.post(
            reverse("register"),
            {"username": "ayse", "email": "ayse@example.com", "password1": PASSWORD, "password2": PASSWORD},
            follow=True,
        )
        self.assertContains(response, "@ayse")
        self.assertNotContains(response, "ayse@example.com")
