from django.test import TestCase
from django.urls import reverse

from accounts.models import User


class HomePageTests(TestCase):
    def test_home_renders_for_visitor(self):
        response = self.client.get(reverse("poll_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Kararsız mı kaldın?")
        self.assertContains(response, "Henüz anket yok")
        self.assertContains(response, "css/main.css")

    def test_home_shows_username_but_never_email(self):
        user = User.objects.create_user("ayse", "ayse@example.com", "guclu-parola-123")
        self.client.force_login(user)
        response = self.client.get(reverse("poll_list"))
        self.assertContains(response, "@ayse")
        self.assertNotContains(response, "ayse@example.com")
