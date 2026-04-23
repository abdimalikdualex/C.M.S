from django.contrib.auth.backends import ModelBackend
from django.contrib.auth import get_user_model


class EmailBackend(ModelBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        # Django passes the identifier in `username`; allow explicit email too.
        email = (kwargs.get("email") or username or "").strip()
        if not email or not password:
            return None

        UserModel = get_user_model()
        try:
            user = UserModel.objects.get(email__iexact=email)
        except UserModel.DoesNotExist:
            return None

        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
