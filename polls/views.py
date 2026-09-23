from django.shortcuts import render


def poll_list(request):
    """Home feed. Phase 0: hero + empty state only; real polls arrive in Phase 2."""
    return render(request, "polls/poll_list.html")
