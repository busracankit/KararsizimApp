from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import IntegrityError, transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .forms import PollCreateForm
from .models import MAX_OPTIONS, MIN_OPTIONS, Poll, Vote
from .services import build_results, existing_vote, polls_with_counts, votes_by_poll

POLLS_PER_PAGE = 10

# ?sirala= values for the feed tabs -> ordering
SORTS = {
    "yeni": ("-created_at", "-id"),
    "populer": ("-total_votes", "-created_at", "-id"),
}
DEFAULT_SORT = "yeni"


def _attach_vote_state(request, polls):
    """Set poll.has_voted and poll.results (when voted) for rendering cards."""
    voted = votes_by_poll(request, [p.pk for p in polls])
    for poll in polls:
        poll.has_voted = poll.pk in voted
        if poll.has_voted:
            poll.results = build_results(poll, voted[poll.pk])


def _paginate(request, queryset):
    page = Paginator(queryset, POLLS_PER_PAGE).get_page(request.GET.get("sayfa"))
    _attach_vote_state(request, page.object_list)
    page_range = page.paginator.get_elided_page_range(page.number, on_each_side=1, on_ends=1)
    return page, page_range


def poll_list(request):
    sort = request.GET.get("sirala", DEFAULT_SORT)
    if sort not in SORTS:
        sort = DEFAULT_SORT
    page, page_range = _paginate(request, polls_with_counts().order_by(*SORTS[sort]))
    return render(request, "polls/poll_list.html", {"page": page, "page_range": page_range, "sort": sort})


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
    """Record one vote. JSON for fetch() calls (API contract: plan §5.2), redirect otherwise."""
    poll = get_object_or_404(Poll, pk=pk)
    as_json = _wants_json(request)

    try:
        option = poll.options.get(pk=int(request.POST.get("option_id", "")))
    except (ValueError, poll.options.model.DoesNotExist):
        if as_json:
            return JsonResponse({"ok": False, "error": "invalid_option"}, status=400)
        messages.error(request, "Geçersiz seçenek. Lütfen tekrar dene.")
        return redirect(poll)

    previous = existing_vote(request, poll)
    if previous is None:
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

    if previous is not None:
        mine = previous.user_id is None or previous.user_id == getattr(request.user, "pk", None)
        payload = build_results(poll, previous.option_id if mine else None)
        if as_json:
            return JsonResponse({"ok": False, "error": "already_voted", **_public(payload)}, status=409)
        messages.info(request, "Bu ankete zaten oy vermişsin.")
        return redirect(poll)

    payload = build_results(poll, option.pk)
    if as_json:
        return JsonResponse({"ok": True, **_public(payload)})
    messages.success(request, "Oyun kaydedildi ✓")
    return redirect(poll)


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
