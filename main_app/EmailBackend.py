from django.contrib.auth.backends import ModelBackend
from django.contrib.auth import get_user_model
from django.db import DatabaseError

from .admission_numbers import is_valid_admission_number, normalize_admission_input
from .models import Student


class EmailBackend(ModelBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        # Django passes the identifier in `username`; allow explicit email too.
        identifier = (kwargs.get("email") or kwargs.get("username") or username or "").strip()
        if not identifier or not password:
            return None

        try:
            normalized_adm = normalize_admission_input(identifier)
            looks_like_student_login = is_valid_admission_number(
                normalized_adm
            ) or Student.objects.filter(student_id__iexact=normalized_adm).exists()

            if looks_like_student_login:
                return self._authenticate_student_admission(identifier, password)

            return self._authenticate_email(identifier, password)
        except DatabaseError:
            return None

    def _authenticate_email(self, email: str, password: str):
        UserModel = get_user_model()
        normalized = email.lower()

        try:
            user = UserModel.objects.get(email__iexact=email)
        except UserModel.DoesNotExist:
            user = None
            for candidate in UserModel.objects.all().only("id", "email", "password", "is_active"):
                if (candidate.email or "").strip().lower() == normalized:
                    user = candidate
                    break

        if user is None:
            return None

        # Learners must sign in with admission number (handled in _authenticate_student_admission).
        if str(getattr(user, "user_type", "") or "").strip() == "3":
            return None

        if user.check_password(password) and self.user_can_authenticate(user):
            return user

        if user.password == password and self.user_can_authenticate(user):
            user.set_password(password)
            user.save(update_fields=["password"])
            return user

        return None

    def _authenticate_student_admission(self, raw_identifier: str, password: str):
        """Students (user_type='3') log in with official admission number, not email."""
        normalized = normalize_admission_input(raw_identifier).strip()
        if not normalized:
            return None

        try:
            student = Student.objects.select_related("admin").get(student_id__iexact=normalized)
        except Student.DoesNotExist:
            return None

        user = student.admin
        if str(getattr(user, "user_type", "") or "").strip() != "3":
            return None

        if user.check_password(password) and self.user_can_authenticate(user):
            return user

        if user.password == password and self.user_can_authenticate(user):
            user.set_password(password)
            user.save(update_fields=["password"])
            return user

        return None
