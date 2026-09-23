from django.contrib.auth.models import AbstractUser
from django.core.validators import MinLengthValidator, RegexValidator
from django.db import models
from django.db.models.functions import Lower

username_validator = RegexValidator(
    regex=r"^[A-Za-z0-9_.]+$",
    message="Kullanıcı adı sadece harf (a-z), rakam, _ ve . içerebilir.",
)


class User(AbstractUser):
    """Custom user: unique username (shown publicly) and unique email (never shown)."""

    username = models.CharField(
        "kullanıcı adı",
        max_length=30,
        unique=True,
        validators=[MinLengthValidator(3), username_validator],
        help_text="3–30 karakter; harf, rakam, _ ve . kullanılabilir.",
        error_messages={"unique": "Bu kullanıcı adı zaten alınmış."},
    )
    email = models.EmailField(
        "e-posta",
        unique=True,
        error_messages={"unique": "Bu e-posta adresiyle zaten bir hesap var."},
    )

    # Not used in this project.
    first_name = None
    last_name = None

    REQUIRED_FIELDS = ["email"]

    class Meta:
        verbose_name = "kullanıcı"
        verbose_name_plural = "kullanıcılar"
        constraints = [
            models.UniqueConstraint(Lower("username"), name="unique_username_ci"),
            models.UniqueConstraint(Lower("email"), name="unique_email_ci"),
        ]

    def save(self, *args, **kwargs):
        if self.email:
            self.email = self.email.strip().lower()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.username
