from datetime import timedelta

from django import forms
from django.db import transaction
from django.utils import timezone

from .models import CATEGORIES, DEFAULT_CATEGORY, MAX_OPTIONS, MIN_OPTIONS, Option, Poll

OPTION_MAX_LENGTH = Option._meta.get_field("text").max_length

# value -> (label, duration or None for "no end")
DURATIONS = {
    "": ("Süresiz", None),
    "1s": ("1 saat", timedelta(hours=1)),
    "1g": ("1 gün", timedelta(days=1)),
    "3g": ("3 gün", timedelta(days=3)),
    "1h": ("1 hafta", timedelta(weeks=1)),
}


def comparison_key(text):
    """Case-insensitive key that respects Turkish İ/i and I/ı ("SİNEMA" == "sinema")."""
    return text.replace("İ", "i").replace("I", "ı").casefold()


class PollCreateForm(forms.Form):
    """Question + 2–5 options.

    Options arrive as repeated ``options`` inputs (``request.POST.getlist``) so the
    number of fields can change on the client. Blank fields are ignored; the
    remaining ones must be 2–5, at most 100 characters and unique (case-insensitive).
    """

    question = forms.CharField(
        label="Sorun ne?",
        min_length=5,
        max_length=200,
        widget=forms.TextInput(
            attrs={"placeholder": "Örn. Bugün sinemaya mı gitsem, restorana mı?", "autocomplete": "off"}
        ),
        error_messages={
            "required": "Soruyu yazmalısın.",
            "min_length": "Soru en az 5 karakter olmalı.",
            "max_length": "Soru en fazla 200 karakter olabilir.",
        },
    )

    category = forms.ChoiceField(
        label="Kategori",
        choices=[(slug, f"{emoji} {label}") for slug, (label, emoji) in CATEGORIES.items()],
        initial=DEFAULT_CATEGORY,
        required=False,
        error_messages={"invalid_choice": "Geçersiz kategori."},
    )
    duration = forms.ChoiceField(
        label="Oylama ne kadar açık kalsın?",
        choices=[(value, label) for value, (label, _) in DURATIONS.items()],
        required=False,
        initial="",
    )

    def __init__(self, data=None, *args, **kwargs):
        super().__init__(data, *args, **kwargs)
        raw = data.getlist("options") if data is not None else []
        # Values shown back in the form: at least 2 inputs, at most 5.
        self.option_values = (list(raw) + ["", ""])[: max(MIN_OPTIONS, min(len(raw), MAX_OPTIONS))]
        self.option_errors = {}  # input index -> message
        self.options_error = None  # error about the option list as a whole

    def clean(self):
        cleaned = super().clean()
        raw = self.data.getlist("options")
        options, seen = [], {}
        for index, value in enumerate(raw):
            text = value.strip()
            if not text:
                continue
            if len(text) > OPTION_MAX_LENGTH:
                self.option_errors[index] = f"Seçenek en fazla {OPTION_MAX_LENGTH} karakter olabilir."
                continue
            key = comparison_key(text)
            if key in seen:
                self.option_errors[index] = "Bu seçeneği zaten yazdın."
                continue
            seen[key] = index
            options.append(text)

        if len(raw) > MAX_OPTIONS or len(options) > MAX_OPTIONS:
            self.options_error = f"En fazla {MAX_OPTIONS} seçenek ekleyebilirsin."
        elif len(options) < MIN_OPTIONS and not self.option_errors:
            self.options_error = f"En az {MIN_OPTIONS} seçenek yazmalısın."

        if self.option_errors or self.options_error:
            raise forms.ValidationError("Seçenekleri kontrol et.", code="options")
        cleaned["options"] = options
        return cleaned

    @transaction.atomic
    def save(self, author):
        length = DURATIONS[self.cleaned_data.get("duration") or ""][1]
        poll = Poll.objects.create(
            author=author,
            question=self.cleaned_data["question"],
            category=self.cleaned_data.get("category") or DEFAULT_CATEGORY,
            closes_at=timezone.now() + length if length else None,
        )
        Option.objects.bulk_create(
            Option(poll=poll, text=text, order=order) for order, text in enumerate(self.cleaned_data["options"])
        )
        return poll
