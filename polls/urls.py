from django.urls import path

from . import views

urlpatterns = [
    path("", views.poll_list, name="poll_list"),
    path("anket/yeni/", views.poll_create, name="poll_create"),
    path("anket/<int:pk>/", views.poll_detail, name="poll_detail"),
    path("anket/<int:pk>/oy/", views.poll_vote, name="poll_vote"),
    path("anket/<int:pk>/sil/", views.poll_delete, name="poll_delete"),
    path("anket/<int:pk>/sikayet/", views.poll_report, name="poll_report"),
    path("anket/<int:pk>/yorum/", views.comment_create, name="comment_create"),
    path("yorum/<int:pk>/sil/", views.comment_delete, name="comment_delete"),
    path("kullanici/<str:username>/", views.user_profile, name="user_profile"),
]
