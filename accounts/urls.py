from django.contrib.auth import views as auth_views
from django.urls import path, reverse_lazy

from . import views

urlpatterns = [
    path("kayit/", views.register, name="register"),
    path("giris/", views.login_view, name="login"),
    path("cikis/", views.logout_view, name="logout"),
    # Password reset (e-mail link)
    path("parola-sifirla/", views.RateLimitedPasswordResetView.as_view(), name="password_reset"),
    path(
        "parola-sifirla/gonderildi/",
        auth_views.PasswordResetDoneView.as_view(template_name="accounts/password_reset_done.html"),
        name="password_reset_done",
    ),
    path(
        "parola-sifirla/<uidb64>/<token>/",
        auth_views.PasswordResetConfirmView.as_view(
            template_name="accounts/password_reset_confirm.html",
            success_url=reverse_lazy("password_reset_complete"),
        ),
        name="password_reset_confirm",
    ),
    path(
        "parola-sifirla/tamam/",
        auth_views.PasswordResetCompleteView.as_view(template_name="accounts/password_reset_complete.html"),
        name="password_reset_complete",
    ),
    # Change password while logged in
    path(
        "parola-degistir/",
        auth_views.PasswordChangeView.as_view(
            template_name="accounts/password_change.html", success_url=reverse_lazy("password_change_done")
        ),
        name="password_change",
    ),
    path(
        "parola-degistir/tamam/",
        auth_views.PasswordChangeDoneView.as_view(template_name="accounts/password_change_done.html"),
        name="password_change_done",
    ),
]
