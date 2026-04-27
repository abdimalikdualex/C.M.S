"""
Role-based dashboards (Kenyan short-course college MVP).

CustomUser.user_type: "1" = HOD / Super Admin, "2" = Staff, "3" = Student,
                     "4" = Director (Manager)
Staff.role: instructor | admission | finance

Admission + finance share one operations desk (register, enroll, payments, receipts).

Permission matrix (concise; middleware in main_app.middleware enforces routing,
forms enforce field exposure, and decorators below enforce per-view access):

  Superadmin (HOD)
    - Full access to all admin pages, course/session/staff/student management,
      finance reports, audit log, and dashboards. Cannot access student-only pages.

  Director (Manager)
    - Read-only oversight: KPIs, students, courses, sessions, staff,
      finance summary, reports (CSV/Excel exports).
    - One write capability: activate / close a Session.
    - Cannot: register students, record payments, take attendance, edit any
      operational data. "See everything, change very little."

  Admission/Finance desk (one combined desk)
    - Can: register students (StudentForm with course+session+agreed fee),
      enroll existing students into more courses, record payments, print
      receipts, view/filter students by course->session, view finance reports.
    - Cannot: take attendance, manage assessments, edit grades, manage other
      staff, edit core course definitions outside HOD_ALLOWED_FOR_ADMISSION_DESK.
    - Form rule: StaffForm strips the `course` field for these roles.

  Instructor
    - Can: view assigned course students, take/update attendance, create
      assessments, grade submissions, enter results.
    - Cannot: register students, record payments, view finance reports, manage
      other staff or sessions.
    - Form rule: instructors must have a teaching course assignment.

  Student
    - Can: view own attendance, fees, results, assessments; submit work; apply
      leave; send feedback.
    - Cannot: see any admin/staff page.
"""
from functools import wraps

from django.contrib import messages
from django.shortcuts import redirect
from django.urls import reverse

SUPERADMIN = "superadmin"
DIRECTOR = "director"
ADMISSION_OFFICER = "admission_officer"
INSTRUCTOR = "instructor"
STUDENT = "student"

ROLE_PERMISSIONS = {
    SUPERADMIN: ("all_access",),
    DIRECTOR: (
        "view_students",
        "view_courses",
        "view_sessions",
        "view_staff",
        "view_finance",
        "view_reports",
        "session_set_active",
    ),
    ADMISSION_OFFICER: (
        "students",
        "enrollment",
        "payments",
        "receipts",
        "reports",
    ),
    INSTRUCTOR: ("attendance", "assessments", "view_course_students"),
    STUDENT: ("view_own_data",),
}

# Director is allowed to invoke a small whitelist of HOD-area URLs (so we can
# reuse e.g. set_active_session without duplicating the view). All listed names
# must be read-only or session-control only.
HOD_ALLOWED_FOR_DIRECTOR = frozenset(
    {
        "set_active_session",
        "manage_session",
    }
)

# HOD course tools admission/finance may use without full HOD access.
HOD_ALLOWED_FOR_ADMISSION_DESK = frozenset(
    {"add_course", "manage_course", "edit_course", "delete_course"}
)

# Academic tools — only instructors (not admission desk).
INSTRUCTOR_ONLY_STAFF_URLS = frozenset(
    {
        "staff_my_classes",
        "staff_take_attendance",
        "staff_update_attendance",
        "get_students",
        "save_attendance",
        "get_student_attendance",
        "update_attendance",
        "staff_add_result",
        "edit_student_result",
        "fetch_student_result",
        "staff_assessment_list",
        "staff_assessment_create",
        "staff_assessment_detail",
        "staff_assessment_submissions",
        "staff_assessment_grade",
    }
)

# Desk workflow: register → enroll → pay → reports (same URLs as before).
ADMISSION_DESK_STAFF_URL_NAMES = frozenset(
    {
        "admission_add_student",
        "admission_enroll_existing_student",
        "staff_course_students",
        "staff_students_by_course",
        "staff_finance_reports",
        "staff_record_payment",
        "admission_dashboard",
    }
)


def get_staff_profile(user):
    if getattr(user, "user_type", None) != "2":
        return None
    from .models import Staff

    try:
        return Staff.objects.select_related("course").get(admin=user)
    except Staff.DoesNotExist:
        return None


def get_staff_role_key(user):
    """Raw Staff.role: admission | finance | instructor, or None."""
    staff = get_staff_profile(user)
    if staff is None:
        return None
    return staff.role


def is_admission_desk_staff(user) -> bool:
    staff = get_staff_profile(user)
    return bool(staff and staff.role in ("admission", "finance"))


def get_dashboard_role(user):
    """
    Logical dashboard role for routing and ACL (not always equal to Staff.role).
    Finance staff map to ADMISSION_OFFICER — one combined desk.
    """
    if not user.is_authenticated:
        return None
    ut = str(getattr(user, "user_type", "") or "").strip()
    if ut == "1":
        return SUPERADMIN
    if ut == "3":
        return STUDENT
    if ut == "4":
        return DIRECTOR
    if ut == "2":
        staff = get_staff_profile(user)
        if staff is None:
            return INSTRUCTOR
        if staff.role in ("admission", "finance"):
            return ADMISSION_OFFICER
        return INSTRUCTOR
    return None


def get_post_login_redirect_url(user):
    """Canonical first screen after login (per dashboard role)."""
    role = get_dashboard_role(user)
    if role == SUPERADMIN:
        return reverse("superadmin_dashboard")
    if role == DIRECTOR:
        return reverse("director_dashboard")
    if role == ADMISSION_OFFICER:
        return reverse("admission_dashboard")
    if role == INSTRUCTOR:
        return reverse("instructor_dashboard")
    if role == STUDENT:
        return reverse("student_dashboard")
    return reverse("login_page")


def user_has_permission(user, perm: str) -> bool:
    """Fine-grained check for views or templates (MVP helper)."""
    role = get_dashboard_role(user)
    if role is None:
        return False
    allowed = ROLE_PERMISSIONS.get(role, ())
    if "all_access" in allowed:
        return True
    return perm in allowed


def _denied_redirect(request, friendly_message):
    """Redirect to the user's own dashboard with an explanatory flash."""
    messages.error(request, friendly_message)
    role = get_dashboard_role(request.user)
    if role == SUPERADMIN:
        return redirect(reverse("superadmin_dashboard"))
    if role == DIRECTOR:
        return redirect(reverse("director_dashboard"))
    if role == ADMISSION_OFFICER:
        return redirect(reverse("admission_dashboard"))
    if role == INSTRUCTOR:
        return redirect(reverse("instructor_dashboard"))
    if role == STUDENT:
        return redirect(reverse("student_dashboard"))
    return redirect(reverse("login_page"))


def require_admission_desk(view_func):
    """
    Allow superadmins and admission/finance staff. Belt-and-braces guard for
    sensitive money/registration views; complements main_app.middleware.
    """

    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect(reverse("login_page"))
        role = get_dashboard_role(request.user)
        if role in (SUPERADMIN, ADMISSION_OFFICER):
            return view_func(request, *args, **kwargs)
        return _denied_redirect(
            request, "This action is restricted to admission/finance staff."
        )

    return _wrapped


def require_instructor(view_func):
    """Allow superadmins and instructors only. Used by attendance/grade tools."""

    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect(reverse("login_page"))
        role = get_dashboard_role(request.user)
        if role in (SUPERADMIN, INSTRUCTOR):
            return view_func(request, *args, **kwargs)
        return _denied_redirect(
            request, "This action is restricted to instructors."
        )

    return _wrapped


def require_director(view_func):
    """
    Allow superadmins and directors only. Used by every read-only oversight
    page in director_views and by the session-activation toggle.
    """

    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect(reverse("login_page"))
        role = get_dashboard_role(request.user)
        if role in (SUPERADMIN, DIRECTOR):
            return view_func(request, *args, **kwargs)
        return _denied_redirect(
            request, "This page is restricted to the Manager / Director."
        )

    return _wrapped
