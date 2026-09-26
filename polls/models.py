from django.conf import settings
from django.core.validators import MinLengthValidator
from django.db import models
from django.utils import timezone

MIN_OPTIONS = 2
MAX_OPTIONS = 5

# slug -> (label, emoji). Order here is the order of the filter chips.
CATEGORIES = {
    "gunluk": ("Günlük hayat", "☕"),
    "yemek": ("Yemek & içecek", "🍕"),
    "alisveris": ("Alışveriş & moda", "🛍️"),
    "eglence": ("Film, dizi & müzik", "🎬"),
    "seyahat": ("Seyahat", "✈️"),
    "teknoloji": ("Teknoloji", "📱"),
    "iliskiler": ("İlişkiler", "💬"),
    "kariyer": ("Okul & kariyer", "🎓"),
    "spor": ("Spor & sağlık", "🏃"),
    "diger": ("Diğer", "✨"),
}
DEFAULT_CATEGORY = "diger"


class Poll(models.Model):
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="polls", verbose_name="yazar"
    )
    question = models.CharField("soru", max_length=200, validators=[MinLengthValidator(5)])
    created_at = models.DateTimeField("oluşturulma", auto_now_add=True, db_index=True)
    closes_at = models.DateTimeField("oylama bitişi", null=True, blank=True, help_text="Boşsa anket süresiz açık kalır.")
    category = models.CharField(
        "kategori",
        max_length=20,
        choices=[(slug, label) for slug, (label, _) in CATEGORIES.items()],
        default=DEFAULT_CATEGORY,
        db_index=True,
    )
    is_hidden = models.BooleanField(
        "gizli", default=False, db_index=True, help_text="Gizli anketler akışta görünmez; sadece sahibi ve yöneticiler açabilir."
    )

    class Meta:
        ordering = ["-created_at", "-id"]
        verbose_name = "anket"
        verbose_name_plural = "anketler"

    def __str__(self):
        return self.question

    def get_absolute_url(self):
        from django.urls import reverse

        return reverse("poll_detail", args=[self.pk])

    @property
    def category_label(self):
        return CATEGORIES.get(self.category, CATEGORIES[DEFAULT_CATEGORY])[0]

    @property
    def category_emoji(self):
        return CATEGORIES.get(self.category, CATEGORIES[DEFAULT_CATEGORY])[1]

    @property
    def is_closed(self):
        return self.closes_at is not None and timezone.now() >= self.closes_at


class Option(models.Model):
    poll = models.ForeignKey(Poll, on_delete=models.CASCADE, related_name="options", verbose_name="anket")
    text = models.CharField("seçenek", max_length=100)
    order = models.PositiveSmallIntegerField("sıra", default=0)
    image_url = models.URLField("görsel", max_length=500, blank=True)

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


class RateLimitHit(models.Model):
    """One attempt at a rate-limited action (see polls/ratelimit.py)."""

    scope = models.CharField(max_length=30)
    key = models.CharField(max_length=80)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "hız sınırı kaydı"
        verbose_name_plural = "hız sınırı kayıtları"
        indexes = [models.Index(fields=["scope", "key", "created_at"], name="ratelimit_lookup")]


REPORT_REASONS = {
    "spam": "Spam / reklam",
    "hakaret": "Hakaret veya nefret söylemi",
    "uygunsuz": "Cinsel ya da uygunsuz içerik",
    "kisisel": "Kişisel bilgi paylaşımı",
    "diger": "Diğer",
}
# Unresolved reports needed to hide a poll automatically until a moderator reviews it.
REPORT_AUTO_HIDE_THRESHOLD = 5


class Report(models.Model):
    poll = models.ForeignKey(Poll, on_delete=models.CASCADE, related_name="reports", verbose_name="anket")
    reporter = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="şikayet eden"
    )
    voter_token = models.CharField("ziyaretçi anahtarı", max_length=36)
    reason = models.CharField("sebep", max_length=20, choices=list(REPORT_REASONS.items()))
    note = models.CharField("açıklama", max_length=300, blank=True)
    created_at = models.DateTimeField("tarih", auto_now_add=True)
    resolved = models.BooleanField("incelendi", default=False, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "şikayet"
        verbose_name_plural = "şikayetler"
        constraints = [
            models.UniqueConstraint(fields=["poll", "voter_token"], name="unique_report_per_browser"),
            models.UniqueConstraint(
                fields=["poll", "reporter"], condition=models.Q(reporter__isnull=False), name="unique_report_per_user"
            ),
        ]

    def __str__(self):
        return f"{self.get_reason_display()} → {self.poll}"


class Comment(models.Model):
    poll = models.ForeignKey(Poll, on_delete=models.CASCADE, related_name="comments", verbose_name="anket")
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="comments", verbose_name="yazar"
    )
    text = models.CharField("yorum", max_length=500)
    created_at = models.DateTimeField("tarih", auto_now_add=True)
    is_hidden = models.BooleanField("gizli", default=False, db_index=True)

    class Meta:
        ordering = ["created_at", "id"]
        verbose_name = "yorum"
        verbose_name_plural = "yorumlar"

    def __str__(self):
        return self.text[:60]
