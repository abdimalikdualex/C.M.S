"""
Role-based dashboards (Kenyan short-course college MVP).

CustomUser.user_type: "1" = HOD / Super Admin, "2" = Staff, "3" = Student
Staff.role: instructor | admission | finance

Admission + finance share one operations desk (register, enroll, payments, receipts).
"""
from django.urls import reverse

SUPERADMIN = "superadmin"
ADMISSION_OFFICER = "admission_officer"
INSTRUCTOR = "instructor"
STUDENT = "student"

ROLE_PERMISSIONS = {
    SUPERADMIN: ("all_access",),
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
