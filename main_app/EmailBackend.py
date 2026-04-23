from django.contrib.auth.backends import ModelBackend
from django.contrib.auth import get_user_model


class EmailBackend(ModelBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        # Django passes the identifier in `username`; allow explicit email too.
        email = (kwargs.get("email") or kwargs.get("username") or username or "").strip()
        if not email or not password:
            return None

        UserModel = get_user_model()
        normalized = email.lower()

        try:
            user = UserModel.objects.get(email__iexact=email)
        except UserModel.DoesNotExist:
            # Fallback for legacy rows with accidental whitespace in email field.
            user = None
            for candidate in UserModel.objects.all().only("id", "email", "password", "is_active"):
                if (candidate.email or "").strip().lower() == normalized:
                    user = candidate
                    break

        if user is None:
            return None

        # Standard hashed-password path.
        if user.check_password(password) and self.user_can_authenticate(user):
            return user

        # Legacy compatibility: auto-upgrade plain-text passwords on first login.
        if user.password == password and self.user_can_authenticate(user):
            user.set_password(password)
            user.save(update_fields=["password"])
            return user

        return None
