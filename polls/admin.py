from django.contrib import admin

from .models import MAX_OPTIONS, MIN_OPTIONS, Option, Poll


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
