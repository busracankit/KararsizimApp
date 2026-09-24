from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render

from .forms import PollCreateForm
from .models import MAX_OPTIONS, MIN_OPTIONS, Poll

POLLS_PER_PAGE = 10


def poll_list(request):
    polls = Poll.objects.select_related("author").prefetch_related("options")
    page = Paginator(polls, POLLS_PER_PAGE).get_page(request.GET.get("sayfa"))
    page_range = page.paginator.get_elided_page_range(page.number, on_each_side=1, on_ends=1)
    return render(request, "polls/poll_list.html", {"page": page, "page_range": page_range})


def poll_detail(request, pk):
    poll = get_object_or_404(Poll.objects.select_related("author").prefetch_related("options"), pk=pk)
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
