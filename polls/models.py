from django.conf import settings
from django.core.validators import MinLengthValidator
from django.db import models

MIN_OPTIONS = 2
MAX_OPTIONS = 5


class Poll(models.Model):
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="polls", verbose_name="yazar"
    )
    question = models.CharField("soru", max_length=200, validators=[MinLengthValidator(5)])
    created_at = models.DateTimeField("oluşturulma", auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        verbose_name = "anket"
        verbose_name_plural = "anketler"

    def __str__(self):
        return self.question

    def get_absolute_url(self):
        from django.urls import reverse

        return reverse("poll_detail", args=[self.pk])


class Option(models.Model):
    poll = models.ForeignKey(Poll, on_delete=models.CASCADE, related_name="options", verbose_name="anket")
    text = models.CharField("seçenek", max_length=100)
    order = models.PositiveSmallIntegerField("sıra", default=0)

    class Meta:
        ordering = ["order", "id"]
        verbose_name = "seçenek"
        verbose_name_plural = "seçenekler"
        constraints = [
            models.UniqueConstraint(fields=["poll", "order"], name="unique_option_order_per_poll"),
            models.CheckConstraint(condition=models.Q(order__lte=MAX_OPTIONS - 1), name="option_order_max_4"),
        ]

    def __str__(self):
        return self.text

    @property
    def color_class(self):
        """CSS class for this option's colour: order 0 -> "opt-1" ... order 4 -> "opt-5"."""
        return f"opt-{self.order + 1}"


class Vote(models.Model):
    """One vote per poll per account and per browser (voter_token cookie).

    Members' votes store both ``user`` and ``voter_token`` so that a visitor who
    votes and then logs in on the same browser cannot vote a second time.
    """

    poll = models.ForeignKey(Poll, on_delete=models.CASCADE, related_name="votes", verbose_name="anket")
    option = models.ForeignKey(Option, on_delete=models.CASCADE, related_name="votes", verbose_name="seçenek")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="votes",
        verbose_name="üye",
    )
    voter_token = models.CharField("ziyaretçi anahtarı", max_length=36, null=True, blank=True)
    created_at = models.DateTimeField("oy zamanı", auto_now_add=True)

    class Meta:
        verbose_name = "oy"
        verbose_name_plural = "oylar"
        constraints = [
            models.UniqueConstraint(
                fields=["poll", "user"], condition=models.Q(user__isnull=False), name="unique_vote_per_user"
            ),
            models.UniqueConstraint(
                fields=["poll", "voter_token"],
                condition=models.Q(voter_token__isnull=False),
                name="unique_vote_per_token",
            ),
            models.CheckConstraint(
                condition=models.Q(user__isnull=False) | models.Q(voter_token__isnull=False),
                name="vote_has_user_or_token",
            ),
        ]

    def __str__(self):
        return f"{self.poll_id} → {self.option}"
