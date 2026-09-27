from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth import views as auth_views
from django.db import IntegrityError
from django.urls import reverse_lazy
from django.shortcuts import redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from polls.ratelimit import hit_rate_limit

from .forms import LoginForm, RegisterForm

TOO_MANY = "Çok fazla deneme yaptın. Biraz bekleyip tekrar dene."

EMAIL_BACKEND = "accounts.backends.EmailBackend"


def _safe_next(request, default):
    """Return the ?next= target if it points to this site, otherwise `default`."""
    target = request.POST.get("next") or request.GET.get("next")
    if target and url_has_allowed_host_and_scheme(
        target, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return target
    return default


def register(request):
    if request.user.is_authenticated:
        return redirect("poll_list")
    form = RegisterForm(request.POST or None)
    if request.method == "POST" and hit_rate_limit(request, "register"):
        messages.error(request, TOO_MANY)
        return render(request, "accounts/register.html", {"form": RegisterForm(), "next": _safe_next(request, "")}, status=429)
    if request.method == "POST" and form.is_valid():
        try:
            user = form.save()
        except IntegrityError:
            # Two sign-ups with the same username/e-mail at the same moment (e.g. a double click):
            # the database rejects the second one; show a form error instead of a 500 page.
            form.add_error(None, "Bu kullanıcı adı ya da e-posta az önce alındı. Başka bir tane dene.")
            return render(request, "accounts/register.html", {"form": form, "next": _safe_next(request, "")})
        login(request, user, backend=EMAIL_BACKEND)
        messages.success(request, f"Hoş geldin @{user.username}! 🎉")
        return redirect(_safe_next(request, "poll_list"))
    return render(request, "accounts/register.html", {"form": form, "next": _safe_next(request, "")})


def login_view(request):
    if request.user.is_authenticated:
        return redirect("poll_list")
    if request.method == "POST" and (
        hit_rate_limit(request, "login")
        or hit_rate_limit(request, "login_account", suffix=request.POST.get("email", "").strip().lower())
    ):
        messages.error(request, TOO_MANY)
        return render(request, "accounts/login.html", {"form": LoginForm(request=request), "next": _safe_next(request, "")}, status=429)
    form = LoginForm(request.POST or None, request=request)
    if request.method == "POST" and form.is_valid():
        login(request, form.user, backend=EMAIL_BACKEND)
        messages.success(request, f"Tekrar hoş geldin @{form.user.username}!")
        return redirect(_safe_next(request, settings.LOGIN_REDIRECT_URL))
    return render(request, "accounts/login.html", {"form": form, "next": _safe_next(request, "")})


@require_POST
def logout_view(request):
    logout(request)
    messages.info(request, "Çıkış yaptın. Görüşmek üzere 👋")
    return redirect(settings.LOGOUT_REDIRECT_URL)


class RateLimitedPasswordResetView(auth_views.PasswordResetView):
    """Same response whether or not the address exists (no account enumeration)."""

    template_name = "accounts/password_reset_form.html"
    email_template_name = "accounts/emails/password_reset.txt"
    html_email_template_name = "accounts/emails/password_reset.html"
    subject_template_name = "accounts/emails/password_reset_subject.txt"
    success_url = reverse_lazy("password_reset_done")

    def form_valid(self, form):
        if hit_rate_limit(self.request, "password_reset"):
            messages.error(self.request, TOO_MANY)
            return self.form_invalid(form)
        return super().form_valid(form)
