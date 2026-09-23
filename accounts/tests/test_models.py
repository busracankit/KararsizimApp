from django.db import IntegrityError, transaction
from django.test import TestCase

from accounts.models import User


class UserModelTests(TestCase):
    def test_email_is_lowercased_on_save(self):
        user = User.objects.create_user("ayse", "  Ayse@Example.COM ", "guclu-parola-123")
        self.assertEqual(user.email, "ayse@example.com")

    def test_username_unique_case_insensitive(self):
        User.objects.create_user("Ayse", "a@example.com", "guclu-parola-123")
        with self.assertRaises(IntegrityError), transaction.atomic():
            User.objects.create_user("ayse", "b@example.com", "guclu-parola-123")

    def test_email_unique_case_insensitive(self):
        User.objects.create_user("ayse", "a@example.com", "guclu-parola-123")
        with self.assertRaises(IntegrityError), transaction.atomic():
            User.objects.create_user("mehmet", "A@Example.com", "guclu-parola-123")

    def test_superuser_can_be_created(self):
        admin = User.objects.create_superuser("admin", "admin@example.com", "guclu-parola-123")
        self.assertTrue(admin.is_superuser)
