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
