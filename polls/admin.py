from django.contrib import admin, messages
from django.db.models import Count, Q

from .models import MAX_OPTIONS, MIN_OPTIONS, Comment, Option, Poll, Report, Vote

admin.site.site_header = "Kararsızım yönetim"
admin.site.site_title = "Kararsızım yönetim"
admin.site.index_title = "Moderasyon ve içerik"


class OptionInline(admin.TabularInline):
    model = Option
    extra = 0
    min_num = MIN_OPTIONS
    max_num = MAX_OPTIONS


class ReportInline(admin.TabularInline):
    model = Report
    extra = 0
    can_delete = False
    fields = ("reason", "note", "reporter", "created_at", "resolved")
    readonly_fields = ("reason", "note", "reporter", "created_at")


@admin.register(Poll)
class PollAdmin(admin.ModelAdmin):
    list_display = ("question", "author", "category", "created_at", "closes_at", "open_reports", "is_hidden")
    list_select_related = ("author",)
    list_filter = ("is_hidden", "category", "created_at")
    search_fields = ("question", "author__username")
    date_hierarchy = "created_at"
    autocomplete_fields = ("author",)
    inlines = [OptionInline, ReportInline]
    actions = ["hide_polls", "unhide_polls"]

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(
            _open_reports=Count("reports", filter=Q(reports__resolved=False))
        )

    @admin.display(description="açık şikayet", ordering="_open_reports")
    def open_reports(self, obj):
        return obj._open_reports

    @admin.action(description="Seçili anketleri gizle")
    def hide_polls(self, request, queryset):
        count = queryset.update(is_hidden=True)
        self.message_user(request, f"{count} anket gizlendi.", messages.SUCCESS)

    @admin.action(description="Seçili anketleri göster ve şikayetlerini incelendi say")
    def unhide_polls(self, request, queryset):
        count = queryset.update(is_hidden=False)
        Report.objects.filter(poll__in=queryset).update(resolved=True)
        self.message_user(request, f"{count} anket yeniden görünür.", messages.SUCCESS)


@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    list_display = ("poll", "reason", "note", "reporter", "created_at", "resolved")
    list_filter = ("resolved", "reason", "created_at")
    list_select_related = ("poll", "reporter")
    search_fields = ("poll__question", "note")
    readonly_fields = ("poll", "reporter", "voter_token", "reason", "note", "created_at")
    actions = ["mark_resolved", "hide_reported_polls"]

    def has_add_permission(self, request):
        return False

    @admin.action(description="İncelendi olarak işaretle")
    def mark_resolved(self, request, queryset):
        self.message_user(request, f"{queryset.update(resolved=True)} şikayet incelendi.", messages.SUCCESS)

    @admin.action(description="Şikayet edilen anketleri gizle ve incelendi say")
    def hide_reported_polls(self, request, queryset):
        polls = Poll.objects.filter(reports__in=queryset).distinct()
        count = polls.update(is_hidden=True)
        queryset.update(resolved=True)
        self.message_user(request, f"{count} anket gizlendi.", messages.SUCCESS)


@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ("text", "author", "poll", "created_at", "is_hidden")
    list_filter = ("is_hidden", "created_at")
    list_select_related = ("author", "poll")
    search_fields = ("text", "author__username", "poll__question")
    readonly_fields = ("poll", "author", "created_at")
    actions = ["hide_comments", "unhide_comments"]

    @admin.action(description="Seçili yorumları gizle")
    def hide_comments(self, request, queryset):
        self.message_user(request, f"{queryset.update(is_hidden=True)} yorum gizlendi.", messages.SUCCESS)

    @admin.action(description="Seçili yorumları göster")
    def unhide_comments(self, request, queryset):
        self.message_user(request, f"{queryset.update(is_hidden=False)} yorum görünür.", messages.SUCCESS)


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
