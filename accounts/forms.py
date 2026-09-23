from django import forms
from django.contrib.auth import authenticate, password_validation

from .models import User, username_validator


class RegisterForm(forms.Form):
    username = forms.CharField(
        label="Kullanıcı adı",
        min_length=3,
        max_length=30,
        validators=[username_validator],
        help_text="3–30 karakter; harf (a-z), rakam, _ ve . kullanılabilir. Herkese görünür.",
        widget=forms.TextInput(attrs={"autocomplete": "username", "autocapitalize": "none", "spellcheck": "false"}),
        error_messages={
            "required": "Kullanıcı adı zorunlu.",
            "min_length": "Kullanıcı adı en az 3 karakter olmalı.",
            "max_length": "Kullanıcı adı en fazla 30 karakter olabilir.",
        },
    )
    email = forms.EmailField(
        label="E-posta",
        help_text="Giriş için kullanılır, hiçbir yerde gösterilmez.",
        widget=forms.EmailInput(attrs={"autocomplete": "email"}),
        error_messages={"required": "E-posta zorunlu.", "invalid": "Geçerli bir e-posta adresi gir."},
    )
    password1 = forms.CharField(
        label="Parola",
        strip=False,
        help_text="En az 8 karakter; sadece rakamlardan oluşmasın.",
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
        error_messages={"required": "Parola zorunlu."},
    )
    password2 = forms.CharField(
        label="Parola (tekrar)",
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
        error_messages={"required": "Parolayı tekrar yaz."},
    )

    def clean_username(self):
        username = self.cleaned_data["username"].strip()
        if User.objects.filter(username__iexact=username).exists():
            raise forms.ValidationError("Bu kullanıcı adı zaten alınmış.")
        return username

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("Bu e-posta adresiyle zaten bir hesap var.")
        return email

    def clean(self):
        cleaned = super().clean()
        p1, p2 = cleaned.get("password1"), cleaned.get("password2")
        if p1 and p2 and p1 != p2:
            self.add_error("password2", "Parolalar eşleşmiyor.")
        elif p1:
            # Validate against a draft user so the similarity check can compare
            # the password with the username / email.
            draft = User(username=cleaned.get("username", ""), email=cleaned.get("email", ""))
            try:
                password_validation.validate_password(p1, draft)
            except forms.ValidationError as error:
                self.add_error("password1", error)
        return cleaned

    def save(self):
        return User.objects.create_user(
            username=self.cleaned_data["username"],
            email=self.cleaned_data["email"],
            password=self.cleaned_data["password1"],
        )


class LoginForm(forms.Form):
    email = forms.EmailField(
        label="E-posta",
        widget=forms.EmailInput(attrs={"autocomplete": "email", "autofocus": True}),
        error_messages={"required": "E-posta zorunlu.", "invalid": "Geçerli bir e-posta adresi gir."},
    )
    password = forms.CharField(
        label="Parola",
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "current-password"}),
        error_messages={"required": "Parola zorunlu."},
    )

    def __init__(self, *args, request=None, **kwargs):
        self.request = request
        self.user = None
        super().__init__(*args, **kwargs)

    def clean(self):
        cleaned = super().clean()
        email, password = cleaned.get("email"), cleaned.get("password")
        if email and password:
            self.user = authenticate(self.request, email=email, password=password)
            if self.user is None:
                raise forms.ValidationError("E-posta veya parola hatalı.")
        return cleaned
