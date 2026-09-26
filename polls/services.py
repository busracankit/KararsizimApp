"""Vote counting and "has this visitor voted?" lookups shared by views and templates."""
from django.db.models import Count, IntegerField, OuterRef, Prefetch, Q, Subquery
from django.db.models.functions import Coalesce

from .models import Comment, Option, Poll, Vote


def _count_subquery(model, **filters):
    rows = model.objects.filter(poll=OuterRef("pk"), **filters).order_by().values("poll")
    return Coalesce(Subquery(rows.annotate(n=Count("pk")).values("n")[:1], output_field=IntegerField()), 0)


def polls_with_counts():
    """Polls with author, vote and comment counts, and options annotated with their vote counts.

    Counts are correlated subqueries (not JOIN + GROUP BY) so they stay correct and cheap
    when combined with each other and with search filters.
    """
    options = Option.objects.annotate(votes_count=Count("votes")).order_by("order", "id")
    return (
        Poll.objects.select_related("author")
        .annotate(
            total_votes=_count_subquery(Vote),
            comment_count=_count_subquery(Comment, is_hidden=False),
        )
        .prefetch_related(Prefetch("options", queryset=options))
        .order_by("-created_at", "-id")
    )


def visible_polls():
    """Polls shown in public lists (feed, search, profiles)."""
    return polls_with_counts().filter(is_hidden=False)


def can_view(user, poll):
    return not poll.is_hidden or user.is_staff or user == poll.author


def percent(votes, total):
    """Whole-number percentage, rounded half up; 0 when there are no votes."""
    if not total:
        return 0
    return int(votes * 100 / total + 0.5)


def build_results(poll, voted_option_id=None):
    """Per-option results for a poll fetched with ``polls_with_counts`` (or plain)."""
    options = list(poll.options.all())
    counts = {o.pk: getattr(o, "votes_count", None) for o in options}
    if None in counts.values():  # not annotated: count directly
        counts = dict(
            Option.objects.filter(poll=poll).annotate(n=Count("votes")).values_list("pk", "n")
        )
    total = sum(counts.values())
    top = max(counts.values(), default=0)
    return {
        "total_votes": total,
        "voted_option_id": voted_option_id,
        "results": [
            {
                "id": o.pk,
                "text": o.text,
                "order": o.order,
                "color_class": o.color_class,
                "votes": counts[o.pk],
                "percent": percent(counts[o.pk], total),
                "is_winner": top > 0 and counts[o.pk] == top,
                "is_mine": o.pk == voted_option_id,
            }
            for o in options
        ],
    }


def _voter_filter(request):
    token = getattr(request, "voter_token", None)
    condition = Q(voter_token=token) if token else Q(pk__in=[])
    if request.user.is_authenticated:
        condition |= Q(user=request.user)
    return condition


def votes_by_poll(request, poll_ids):
    """{poll_id: option_id or None} for polls this browser/account already voted in (one query).

    The value is None when the only matching vote was cast on this browser by a
    *different* account: voting is blocked, but it is not shown as "your vote".
    """
    found = {}
    me = request.user.pk if request.user.is_authenticated else None
    for poll_id, option_id, user_id in Vote.objects.filter(_voter_filter(request), poll_id__in=poll_ids).values_list(
        "poll_id", "option_id", "user_id"
    ):
        mine = user_id is None or user_id == me
        if mine or poll_id not in found:
            found[poll_id] = option_id if mine else None
    return found


def existing_vote(request, poll):
    return Vote.objects.filter(_voter_filter(request), poll=poll).first()
