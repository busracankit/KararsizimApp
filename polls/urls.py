from django.urls import path

from . import views

urlpatterns = [
    path("", views.poll_list, name="poll_list"),
]
