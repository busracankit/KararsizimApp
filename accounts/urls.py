from django.urls import path

from . import views

urlpatterns = [
    path("kayit/", views.register, name="register"),
    path("giris/", views.login_view, name="login"),
    path("cikis/", views.logout_view, name="logout"),
]
