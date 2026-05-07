from django.urls import resolve, reverse
from django.utils.deprecation import MiddlewareMixin
from django.shortcuts import redirect


class LoginCheckMiddleWare(MiddlewareMixin):
    """
    URL-area routing for the ICT Hub edition.

    Three active roles only:
      * Superadmin (CustomUser.user_type in {"1", "4"}) — full access except
        student-only views. ut="4" is the legacy Director column folded in.
      * Instructor (CustomUser.user_type == "2") — staff/assessment area only.
        Legacy admission/finance staff also land here; they can browse the
        instructor pages but have no course assignment so they see empty
        listings (effective soft-deactivation without a destructive migration).
      * Student   (CustomUser.user_type == "3") — student area only.
    """

    def process_view(self, request, view_func, view_args, view_kwargs):
        modulename = view_func.__module__
        user = request.user

        try:
            match = resolve(request.path)
            url_name = match.url_name  # noqa: F841 — kept for future per-URL rules
        except Exception:
            url_name = None  # noqa: F841

        if not user.is_authenticated:
            if request.path in (reverse("login_page"), reverse("user_login")):
                return None
            if modulename == "django.contrib.auth.views":
                return None
            return redirect(reverse("login_page"))

        ut = str(getattr(user, "user_type", "") or "").strip()

        # Superadmin (and legacy Director rows folded in).
        if ut in ("1", "4"):
            if modulename == "main_app.student_views":
                return redirect(reverse("superadmin_dashboard"))
            return None

        # Student.
        if ut == "3":
            if modulename in ("main_app.hod_views", "main_app.staff_views", "main_app.EditResultView"):
                return redirect(reverse("student_dashboard"))
            if modulename == "main_app.views" and url_name == "get_attendance":
                return redirect(reverse("student_dashboard"))
            return None

        # Instructor (and any legacy admission/finance staff folded in).
        if ut == "2":
            if modulename in ("main_app.billing_views", "main_app.student_views"):
                return redirect(reverse("instructor_dashboard"))
            if modulename == "main_app.hod_views":
                return redirect(reverse("instructor_dashboard"))
            return None

        return redirect(reverse("login_page"))
