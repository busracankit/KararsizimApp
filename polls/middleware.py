import uuid

from django.conf import settings

VOTER_COOKIE_NAME = "kararsizim_vid"
VOTER_COOKIE_MAX_AGE = 60 * 60 * 24 * 365  # 1 year


def _valid_token(value):
    try:
        return str(uuid.UUID(value, version=4)) == value
    except (TypeError, ValueError, AttributeError):
        return False


class VoterCookieMiddleware:
    """Give every browser a random, anonymous ID used to limit votes to one per poll.

    Sets ``request.voter_token``; if the cookie is missing or malformed a new UUID4
    is generated and written on the response.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        token = request.COOKIES.get(VOTER_COOKIE_NAME)
        is_new = not _valid_token(token)
        if is_new:
            token = str(uuid.uuid4())
        request.voter_token = token

        response = self.get_response(request)

        if is_new:
            response.set_cookie(
                VOTER_COOKIE_NAME,
                token,
                max_age=VOTER_COOKIE_MAX_AGE,
                httponly=True,
                samesite="Lax",
                secure=not settings.DEBUG,
            )
        return response
