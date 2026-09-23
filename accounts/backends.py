from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend


class EmailBackend(ModelBackend):
    """Authenticate with email + password (case-insensitive email).

    Called as ``authenticate(request, email=..., password=...)``. Username-based
    logins (e.g. the Django admin) fall through to the regular ModelBackend.
    """

    def authenticate(self, request, email=None, password=None, **kwargs):
        if email is None or password is None:
            return None
        User = get_user_model()
        try:
            user = User.objects.get(email__iexact=email.strip())
        except User.DoesNotExist:
            # Run the hasher anyway to reduce timing differences between
            # "no such user" and "wrong password".
            User().set_password(password)
            return None
        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
