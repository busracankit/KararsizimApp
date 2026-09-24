from django.urls import path

from . import views

urlpatterns = [
    path("", views.poll_list, name="poll_list"),
    path("anket/yeni/", views.poll_create, name="poll_create"),
    path("anket/<int:pk>/", views.poll_detail, name="poll_detail"),
    path("anket/<int:pk>/oy/", views.poll_vote, name="poll_vote"),
]
