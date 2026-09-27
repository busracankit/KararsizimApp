from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import IntegrityError, transaction
from django.db.models import Exists, OuterRef, Q
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import urlencode
from django.views.decorators.http import require_POST

from .forms import CommentForm, PollCreateForm, ReportForm
from .models import (
    CATEGORIES,
    MAX_OPTIONS,
    MIN_OPTIONS,
    REPORT_AUTO_HIDE_THRESHOLD,
    Comment,
    Option,
    Poll,
    Report,
    Vote,
)
from .ratelimit import hit_rate_limit
from .storage import ImageError, delete_images, uploads_enabled
from .services import build_results, can_view, existing_vote, polls_with_counts, visible_polls, votes_by_poll

POLLS_PER_PAGE = 10

# ?sirala= values for the feed tabs -> ordering
SORTS = {
    "yeni": ("-created_at", "-id"),
    "populer": ("-total_votes", "-created_at", "-id"),
}
DEFAULT_SORT = "yeni"


def _attach_vote_state(request, polls):
    """Set per-poll display state for cards / detail:

    has_voted     this browser/account already voted
    show_results  voted, or voting has closed
    can_change    the vote is this viewer's own and the poll is still open
    results       build_results(...) when show_results
    """
    voted = votes_by_poll(request, [p.pk for p in polls])
    for poll in polls:
        poll.has_voted = poll.pk in voted
        my_option = voted.get(poll.pk)
        poll.show_results = poll.has_voted or poll.is_closed
        poll.can_change = poll.has_voted and my_option is not None and not poll.is_closed
        if poll.show_results:
            poll.results = build_results(poll, my_option)


def _paginate(request, queryset):
    page = Paginator(queryset, POLLS_PER_PAGE).get_page(request.GET.get("sayfa"))
    _attach_vote_state(request, page.object_list)
    page_range = page.paginator.get_elided_page_range(page.number, on_each_side=1, on_ends=1)
    return page, page_range


SEARCH_MAX_LENGTH = 100


def search_variants(text):
    """The query plus a Turkish-uppercased copy.

    Postgres UPPER() maps 'i' to 'I', so "istanbul" would not match "İstanbul".
    Also searching for the Turkish uppercase form ("İSTANBUL") fixes that.
    """
    turkish_upper = text.replace("i", "İ").replace("ı", "I").upper()
    return list(dict.fromkeys([text, turkish_upper]))


def search_polls(queryset, text):
    condition = Q()
    for variant in search_variants(text):
        option_match = Option.objects.filter(poll=OuterRef("pk"), text__icontains=variant)
        condition |= Q(question__icontains=variant) | Exists(option_match)
    return queryset.filter(condition)


def poll_list(request):
    sort = request.GET.get("sirala", DEFAULT_SORT)
    if sort not in SORTS:
        sort = DEFAULT_SORT
    category = request.GET.get("kategori", "")
    if category not in CATEGORIES:
        category = ""
    query = request.GET.get("q", "").strip()[:SEARCH_MAX_LENGTH]

    polls = visible_polls()
    if category:
        polls = polls.filter(category=category)
    if query:
        polls = search_polls(polls, query)
    page, page_range = _paginate(request, polls.order_by(*SORTS[sort]))

    # Current filters, so every link keeps the others.
    params = {"q": query, "kategori": category, "sirala": sort if sort != DEFAULT_SORT else ""}

    def link(**changes):
        merged = {k: v for k, v in {**params, **changes}.items() if v}
        return "?" + urlencode(merged) if merged else "?"

    context = {
        "page": page,
        "page_range": page_range,
        "sort": sort,
        "category": category,
        "query": query,
        "is_filtered": bool(category or query),
        "sort_links": [
            ("yeni", "✨ En yeni", link(sirala="")),
            ("populer", "🔥 En çok oylanan", link(sirala="populer")),
        ],
        "category_links": [("", "Tümü", "🌈", link(kategori=""))]
        + [(slug, label, emoji, link(kategori=slug)) for slug, (label, emoji) in CATEGORIES.items()],
        "extra_query": urlencode({k: v for k, v in params.items() if v}),
        "category_label": CATEGORIES[category][0] if category else "",
    }
    return render(request, "polls/poll_list.html", context)


def user_profile(request, username):
    """Public profile: username, join date and the user's polls. Never shows the email."""
    profile_user = get_object_or_404(get_user_model(), username__iexact=username, is_active=True)
    polls = visible_polls().filter(author=profile_user)
    page, page_range = _paginate(request, polls)
    return render(
        request,
        "polls/user_profile.html",
        {"profile_user": profile_user, "page": page, "page_range": page_range},
    )


def _visible_poll_or_404(request, queryset, pk):
    poll = get_object_or_404(queryset, pk=pk)
    if not can_view(request.user, poll):
        raise Http404
    return poll


def poll_detail(request, pk):
    poll = _visible_poll_or_404(request, polls_with_counts(), pk)
    _attach_vote_state(request, [poll])
    comments = poll.comments.filter(is_hidden=False).select_related("author")
    context = {
        "poll": poll,
        "comments": comments,
        "comment_form": CommentForm(),
        "can_report": request.user != poll.author,
    }
    return render(request, "polls/poll_detail.html", context)


def poll_share_image(request, pk):
    """PNG preview card used as og:image when a poll link is shared."""
    from .share_image import render_poll_card

    poll = get_object_or_404(polls_with_counts(), pk=pk, is_hidden=False)
    png = render_poll_card(poll, list(poll.options.all()), poll.total_votes)
    response = HttpResponse(png, content_type="image/png")
    response["Cache-Control"] = "public, max-age=600, s-maxage=600"
    return response


@login_required
def poll_create(request):
    form = PollCreateForm(*((request.POST, request.FILES) if request.method == "POST" else ()))
    context = {
        "form": form,
        "min_options": MIN_OPTIONS,
        "max_options": MAX_OPTIONS,
        "images_enabled": uploads_enabled(),
    }
    if request.method == "POST" and hit_rate_limit(request, "poll_create"):
        messages.error(request, "Kısa sürede çok fazla anket açtın. Biraz sonra tekrar dene.")
        return render(request, "polls/poll_create.html", context, status=429)
    if request.method == "POST" and form.is_valid():
        if form.has_images and hit_rate_limit(request, "upload"):
            messages.error(request, "Kısa sürede çok fazla görsel yükledin. Görselsiz dene ya da biraz bekle.")
            return render(request, "polls/poll_create.html", context, status=429)
        try:
            poll = form.save(author=request.user)
        except ImageError as error:
            messages.error(request, str(error))
            return render(request, "polls/poll_create.html", context)
        messages.success(request, "Anketin yayında! Linki paylaş, herkes oylasın 🎉")
        return redirect(poll)
    return render(request, "polls/poll_create.html", context)


@login_required
def poll_delete(request, pk):
    """Authors can delete their own poll after a confirmation step (POST only deletes)."""
    poll = get_object_or_404(polls_with_counts(), pk=pk, author=request.user)
    if request.method == "POST":
        image_urls = [option.image_url for option in poll.options.all() if option.image_url]
        poll.delete()
        delete_images(image_urls)
        messages.success(request, "Anketin silindi.")
        return redirect("user_profile", username=request.user.username)
    return render(request, "polls/poll_confirm_delete.html", {"poll": poll})


def poll_report(request, pk):
    """Anyone (visitor or member) can report a poll once per browser/account."""
    poll = _visible_poll_or_404(request, Poll.objects.select_related("author"), pk)
    if request.user == poll.author:
        messages.info(request, "Kendi anketini şikayet edemezsin; istersen silebilirsin.")
        return redirect(poll)
    user = request.user if request.user.is_authenticated else None
    already = Report.objects.filter(poll=poll).filter(
        Q(voter_token=request.voter_token) | (Q(reporter=user) if user else Q(pk__in=[]))
    ).exists()
    if already:
        messages.info(request, "Bu anketi zaten şikayet ettin. Teşekkürler, inceleniyor.")
        return redirect(poll)

    form = ReportForm(request.POST or None)
    if request.method == "POST":
        if hit_rate_limit(request, "report"):
            messages.error(request, "Kısa sürede çok fazla şikayet gönderdin. Biraz sonra tekrar dene.")
            return redirect(poll)
        if form.is_valid():
            try:
                with transaction.atomic():
                    Report.objects.create(
                        poll=poll,
                        reporter=user,
                        voter_token=request.voter_token,
                        reason=form.cleaned_data["reason"],
                        note=form.cleaned_data["note"],
                    )
            except IntegrityError:
                pass
            # Only distinct members count toward auto-hiding. Visitor reports are still stored for
            # moderators, but a visitor can get a fresh cookie on every request, so counting them
            # would let one person hide any poll.
            member_reports = (
                poll.reports.filter(resolved=False, reporter__isnull=False).values("reporter").distinct().count()
            )
            if member_reports >= REPORT_AUTO_HIDE_THRESHOLD and not poll.is_hidden:
                Poll.objects.filter(pk=poll.pk).update(is_hidden=True)
            messages.success(request, "Teşekkürler, şikayetin moderatörlere iletildi.")
            return redirect(poll)
    return render(request, "polls/poll_report.html", {"poll": poll, "form": form})


@login_required
@require_POST
def comment_create(request, pk):
    poll = _visible_poll_or_404(request, Poll.objects.all(), pk)
    if hit_rate_limit(request, "comment"):
        messages.error(request, "Çok hızlı yorum yapıyorsun, biraz bekle.")
        return redirect(f"{poll.get_absolute_url()}#yorumlar")
    form = CommentForm(request.POST)
    if form.is_valid():
        comment = Comment.objects.create(poll=poll, author=request.user, text=form.cleaned_data["text"])
        return redirect(f"{poll.get_absolute_url()}#yorum-{comment.pk}")
    messages.error(request, form.errors["text"][0])
    return redirect(f"{poll.get_absolute_url()}#yorumlar")


@login_required
@require_POST
def comment_delete(request, pk):
    """The comment's author or the poll's author may delete a comment."""
    comment = get_object_or_404(Comment.objects.select_related("poll"), pk=pk)
    if request.user not in (comment.author, comment.poll.author):
        raise Http404
    poll = comment.poll
    comment.delete()
    messages.success(request, "Yorum silindi.")
    return redirect(f"{poll.get_absolute_url()}#yorumlar")


def _wants_json(request):
    return "application/json" in request.headers.get("Accept", "")


@require_POST
def poll_vote(request, pk):
    """Record or change a vote. JSON for fetch() calls (API contract: plan §5.2 + extensions), redirect otherwise.

    Extensions to the original contract:
    - ``change=1`` switches the viewer's own vote while the poll is open (200).
    - 403 ``poll_closed`` once ``closes_at`` has passed (results are still returned).
    - Every results payload also carries ``can_change`` and ``closed``.
    """
    poll = _visible_poll_or_404(request, Poll.objects.all(), pk)
    as_json = _wants_json(request)
    if hit_rate_limit(request, "vote"):
        if as_json:
            return JsonResponse({"ok": False, "error": "rate_limited"}, status=429)
        messages.error(request, "Çok hızlı gidiyorsun, biraz bekleyip tekrar dene.")
        return redirect(poll)
    wants_change = request.POST.get("change") == "1"

    def respond(status, ok, message, level, voted_option_id, can_change, error=None):
        if as_json:
            body = {"ok": ok, **_public(build_results(poll, voted_option_id))}
            body.update(can_change=can_change, closed=poll.is_closed)
            if error:
                body["error"] = error
            return JsonResponse(body, status=status)
        getattr(messages, level)(request, message)
        return redirect(poll)

    try:
        option = poll.options.get(pk=int(request.POST.get("option_id", "")))
    except (ValueError, poll.options.model.DoesNotExist):
        if as_json:
            return JsonResponse({"ok": False, "error": "invalid_option"}, status=400)
        messages.error(request, "Geçersiz seçenek. Lütfen tekrar dene.")
        return redirect(poll)

    previous = existing_vote(request, poll)
    mine = previous is not None and (previous.user_id is None or previous.user_id == getattr(request.user, "pk", None))
    my_option = previous.option_id if mine else None

    if poll.is_closed:
        return respond(403, False, "Bu anketin oylaması kapandı.", "info", my_option, False, "poll_closed")

    if previous is not None:
        if wants_change and mine:
            if previous.option_id != option.pk:
                previous.option = option
                previous.save(update_fields=["option"])
            return respond(200, True, "Oyun güncellendi ✓", "success", option.pk, True)
        return respond(409, False, "Bu ankete zaten oy vermişsin.", "info", my_option, mine, "already_voted")

    if not request.user.is_authenticated and hit_rate_limit(request, "visitor_vote_per_poll", suffix=poll.pk):
        # Many visitor votes for this poll from one network: likely scripted. Members can still vote.
        if as_json:
            return JsonResponse({"ok": False, "error": "login_required"}, status=429)
        messages.info(request, "Bu ağdan bu ankete çok fazla oy verildi. Oy vermek için giriş yap.")
        return redirect(poll)

    try:
        with transaction.atomic():
            Vote.objects.create(
                poll=poll,
                option=option,
                user=request.user if request.user.is_authenticated else None,
                voter_token=request.voter_token,
            )
    except IntegrityError:  # a parallel request won the race
        previous = existing_vote(request, poll)
        return respond(409, False, "Bu ankete zaten oy vermişsin.", "info",
                       previous.option_id if previous else None, False, "already_voted")
    return respond(200, True, "Oyun kaydedildi ✓", "success", option.pk, True)


def _public(payload):
    """Results in the API contract shape: id, text, votes, percent (+ image_url when the option has one)."""
    results = []
    for r in payload["results"]:
        item = {"id": r["id"], "text": r["text"], "votes": r["votes"], "percent": r["percent"]}
        if r["image_url"]:
            item["image_url"] = r["image_url"]
        results.append(item)
    return {
        "total_votes": payload["total_votes"],
        "voted_option_id": payload["voted_option_id"],
        "results": results,
    }
