from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, logout
from django.shortcuts import redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from .forms import LoginForm, RegisterForm

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
    if request.method == "POST" and form.is_valid():
        user = form.save()
        login(request, user, backend=EMAIL_BACKEND)
        messages.success(request, f"Hoş geldin @{user.username}! 🎉")
        return redirect(_safe_next(request, "poll_list"))
    return render(request, "accounts/register.html", {"form": form, "next": _safe_next(request, "")})


def login_view(request):
    if request.user.is_authenticated:
        return redirect("poll_list")
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
