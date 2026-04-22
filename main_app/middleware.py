from django.urls import resolve, reverse
from django.utils.deprecation import MiddlewareMixin
from django.shortcuts import redirect

from .roles import (
    ADMISSION_DESK_STAFF_URL_NAMES,
    ADMISSION_OFFICER,
    HOD_ALLOWED_FOR_ADMISSION_DESK,
    INSTRUCTOR,
    INSTRUCTOR_ONLY_STAFF_URLS,
    get_dashboard_role,
)


class LoginCheckMiddleWare(MiddlewareMixin):
    def process_view(self, request, view_func, view_args, view_kwargs):
        modulename = view_func.__module__
        user = request.user

        try:
            match = resolve(request.path)
            url_name = match.url_name
        except Exception:
            url_name = None

        if not user.is_authenticated:
            if request.path in (reverse("login_page"), reverse("user_login")):
                return None
            if modulename == "django.contrib.auth.views":
                return None
            return redirect(reverse("login_page"))

        ut = str(getattr(user, "user_type", "") or "").strip()
        desk = get_dashboard_role(user)

        if ut == "1":
            if modulename == "main_app.student_views":
                return redirect(reverse("superadmin_dashboard"))
            return None

        if ut == "3":
            if modulename in ("main_app.hod_views", "main_app.staff_views", "main_app.EditResultView"):
                return redirect(reverse("student_dashboard"))
            if modulename == "main_app.views" and url_name == "get_attendance":
                return redirect(reverse("student_dashboard"))
            return None

        if ut == "2":
            if modulename == "main_app.billing_views":
                if desk == ADMISSION_OFFICER:
                    return None
                return redirect(reverse("instructor_dashboard"))

            if modulename == "main_app.student_views":
                if desk == ADMISSION_OFFICER:
                    return redirect(reverse("admission_dashboard"))
                return redirect(reverse("instructor_dashboard"))

            if modulename == "main_app.hod_views":
                if desk == ADMISSION_OFFICER and url_name in HOD_ALLOWED_FOR_ADMISSION_DESK:
                    return None
                if desk == INSTRUCTOR:
                    return redirect(reverse("instructor_dashboard"))
                return redirect(reverse("admission_dashboard"))

            is_staff_area = modulename in (
                "main_app.staff_views",
                "main_app.EditResultView",
                "main_app.assessment_views",
            )
            if is_staff_area:
                if desk == ADMISSION_OFFICER:
                    if url_name in INSTRUCTOR_ONLY_STAFF_URLS:
                        return redirect(reverse("admission_dashboard"))
                    return None
                if desk == INSTRUCTOR:
                    if url_name in ADMISSION_DESK_STAFF_URL_NAMES:
                        return redirect(reverse("instructor_dashboard"))
                    return None
                return None

            return None

        return redirect(reverse("login_page"))
