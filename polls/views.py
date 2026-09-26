from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Exists, OuterRef, Q
from django.utils.http import urlencode
from django.db import IntegrityError, transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .forms import PollCreateForm
from .models import CATEGORIES, MAX_OPTIONS, MIN_OPTIONS, Option, Poll, Vote
from .services import build_results, existing_vote, polls_with_counts, votes_by_poll

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

    polls = polls_with_counts()
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
    polls = polls_with_counts().filter(author=profile_user)
    page, page_range = _paginate(request, polls)
    return render(
        request,
        "polls/user_profile.html",
        {"profile_user": profile_user, "page": page, "page_range": page_range},
    )


def poll_detail(request, pk):
    poll = get_object_or_404(polls_with_counts(), pk=pk)
    _attach_vote_state(request, [poll])
    return render(request, "polls/poll_detail.html", {"poll": poll})


@login_required
def poll_create(request):
    form = PollCreateForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        poll = form.save(author=request.user)
        messages.success(request, "Anketin yayında! Linki paylaş, herkes oylasın 🎉")
        return redirect(poll)
    return render(
        request,
        "polls/poll_create.html",
        {"form": form, "min_options": MIN_OPTIONS, "max_options": MAX_OPTIONS},
    )


@login_required
def poll_delete(request, pk):
    """Authors can delete their own poll after a confirmation step (POST only deletes)."""
    poll = get_object_or_404(polls_with_counts(), pk=pk, author=request.user)
    if request.method == "POST":
        poll.delete()
        messages.success(request, "Anketin silindi.")
        return redirect("user_profile", username=request.user.username)
    return render(request, "polls/poll_confirm_delete.html", {"poll": poll})


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
    poll = get_object_or_404(Poll, pk=pk)
    as_json = _wants_json(request)
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
    """Shape results exactly as the API contract: id, text, votes, percent."""
    return {
        "total_votes": payload["total_votes"],
        "voted_option_id": payload["voted_option_id"],
        "results": [
            {"id": r["id"], "text": r["text"], "votes": r["votes"], "percent": r["percent"]}
            for r in payload["results"]
        ],
    }
