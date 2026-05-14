"""
Academic tooling ACL — Superadmin (user_type 1 / 4) acts as lead instructor.

Superadmins normally have no Staff row; we ensure a dedicated Staff profile exists
so Assessment.instructor / MentorNote.author FKs remain valid. Teaching views
that scope by Subject.staff widen to all active units when the user is Superadmin.
"""

from django.contrib import messages
from django.shortcuts import get_object_or_404

from .models import Session, Staff, Subject


def is_hub_superadmin(user) -> bool:
    return str(getattr(user, "user_type", "") or "").strip() in ("1", "4")


def ensure_academic_staff(request):
    """
    Return Staff for academic views.

    Superadmin: get_or_create an instructor Staff row linked to this user.
    Instructor (user_type 2): must have Staff with role instructor.
    """
    user = request.user
    if is_hub_superadmin(user):
        staff, _ = Staff.objects.get_or_create(
            admin=user,
            defaults={"role": "instructor", "course": None, "is_deleted": False},
        )
        return staff
    try:
        staff = Staff.objects.get(admin=user, is_deleted=False)
    except Staff.DoesNotExist:
        messages.error(request, "You do not have access to this page.")
        return None
    if staff.role != "instructor":
        messages.error(request, "Only instructors can access this page.")
        return None
    return staff


def subjects_for_academic(request, staff):
    """Active subjects the user may use in attendance / results UIs."""
    if is_hub_superadmin(request.user):
        return (
            Subject.objects.filter(is_active=True)
            .select_related("course")
            .order_by("course__name", "sort_order", "name")
        )
    return Subject.objects.filter(staff=staff, is_active=True).select_related("course")


def sessions_for_academic(request, staff):
    """Sessions dropdown scope: all recent for Superadmin; otherwise by assigned courses."""
    if is_hub_superadmin(request.user):
        qs = Session.objects.latest_first()
        return qs if qs.exists() else Session.objects.all().order_by("-id")
    course_ids = Subject.objects.filter(staff=staff, is_active=True).values_list(
        "course_id", flat=True
    )
    qs = (
        Session.objects.filter(enrollments__course_id__in=course_ids)
        .distinct()
        .latest_first()
    )
    if qs.exists():
        return qs
    return Session.objects.active_or_latest()


def user_may_access_subject(request, staff, subject: Subject) -> bool:
    if is_hub_superadmin(request.user):
        return bool(subject.is_active)
    return subject.staff_id == staff.id and subject.is_active


def assessment_queryset_for_user(request, staff):
    from .models import Assessment

    if is_hub_superadmin(request.user):
        return Assessment.objects.all()
    return Assessment.objects.filter(instructor=staff)


def get_assessment_for_academic(request, staff, pk: int):
    from .models import Assessment

    if is_hub_superadmin(request.user):
        return get_object_or_404(Assessment.objects.select_related("course"), pk=pk)
    return get_object_or_404(
        Assessment.objects.select_related("course"),
        pk=pk,
        instructor=staff,
    )


def staff_may_mentor_enrollment(request, staff, enrollment) -> bool:
    if is_hub_superadmin(request.user):
        return True
    if enrollment.assigned_instructor_id == staff.id:
        return True
    if staff.course_id and enrollment.course_id == staff.course_id:
        return True
    return False
