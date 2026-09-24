from django.contrib import admin

from .models import MAX_OPTIONS, MIN_OPTIONS, Option, Poll, Vote


class OptionInline(admin.TabularInline):
    model = Option
    extra = 0
    min_num = MIN_OPTIONS
    max_num = MAX_OPTIONS


@admin.register(Poll)
class PollAdmin(admin.ModelAdmin):
    list_display = ("question", "author", "created_at")
    list_select_related = ("author",)
    search_fields = ("question", "author__username")
    date_hierarchy = "created_at"
    autocomplete_fields = ("author",)
    inlines = [OptionInline]


@admin.register(Vote)
class VoteAdmin(admin.ModelAdmin):
    """Read-only: votes are only created through the site."""

    list_display = ("poll", "option", "user", "voter_token", "created_at")
    list_select_related = ("poll", "option", "user")
    list_filter = ("created_at",)
    search_fields = ("poll__question", "user__username", "voter_token")
    readonly_fields = ("poll", "option", "user", "voter_token", "created_at")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
