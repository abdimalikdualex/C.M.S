"""
Superadmin student register export: shared filters and row helpers (real-time DB data).
"""
from __future__ import annotations

from itertools import groupby

from django.db.models import Q
from django.utils import timezone

from .datetime_display import format_date
from .models import Student


def _enrollment_status_from_get(GET) -> str | None:
    raw = (GET.get("enrollment_status") or GET.get("status") or "").strip()
    if raw in ("active", "completed", "cancelled"):
        return raw
    return None


def describe_export_filters(request) -> str:
    """Human-readable summary of active export filters (for PDF header)."""
    GET = request.GET
    parts = []
    q = (GET.get("q") or "").strip()
    if q:
        parts.append(f'Search "{q}"')
    raw_course = (GET.get("course") or "").strip()
    if raw_course.isdigit():
        from .models import Course

        c = Course.objects.filter(pk=int(raw_course)).values_list("name", flat=True).first()
        if c:
            parts.append(f"Course: {c}")
    raw_session = (GET.get("session") or "").strip()
    if raw_session.isdigit():
        from .models import Session

        s = Session.objects.filter(pk=int(raw_session)).first()
        if s:
            parts.append(f"Session: {s.intake_label}")
    est = _enrollment_status_from_get(GET)
    if est:
        parts.append(f"Enrollment status: {est.title()}")
    if GET.get("pending") == "1":
        parts.append("Outstanding fee balance only")
    if GET.get("new_today") == "1":
        parts.append(f"Enrolled today ({format_date(timezone.localdate())})")
    gb = (GET.get("group_by") or "").strip()
    if gb == "course":
        parts.append("Grouped by course")
    elif gb == "session":
        parts.append("Grouped by session")
    if not parts:
        parts.append("All students (no filters)")
    return " · ".join(parts)


def get_students_for_export_list(request) -> list[Student]:
    """
    Filtered Student rows for register export (matches Manage Students filters).
    """
    GET = request.GET
    qs = Student.objects.select_related("admin", "course", "session").order_by(
        "course__name",
        "session__start_year",
        "admin__full_name",
        "admin__first_name",
        "student_id",
    )

    q = (GET.get("q") or "").strip()
    if q:
        qs = qs.filter(
            Q(admin__first_name__icontains=q)
            | Q(admin__last_name__icontains=q)
            | Q(admin__full_name__icontains=q)
            | Q(admin__phone_number__icontains=q)
            | Q(student_id__icontains=q)
            | Q(course__name__icontains=q)
        )

    raw_session = (GET.get("session") or "").strip()
    if raw_session.isdigit():
        qs = qs.filter(session_id=int(raw_session))

    raw_course = (GET.get("course") or "").strip()
    if raw_course.isdigit():
        qs = qs.filter(course_id=int(raw_course))

    est = _enrollment_status_from_get(GET)
    if est:
        qs = qs.filter(enrollments__status=est).distinct()

    if GET.get("new_today") == "1":
        qs = qs.filter(enrollment_date=timezone.localdate())

    students = list(qs)
    if GET.get("pending") == "1":
        students = [s for s in students if s.balance() > 0]

    gb = (GET.get("group_by") or "").strip()
    if gb == "course":
        students.sort(key=lambda s: ((s.course.name if s.course_id else ""), s.session_id or 0, s.admin.full_name or ""))
    elif gb == "session":
        students.sort(
            key=lambda s: (
                s.session.intake_label if s.session_id else "",
                s.course.name if s.course_id else "",
                s.admin.full_name or "",
            )
        )

    return students


def student_row_cells(st: Student) -> list[str]:
    name = (st.admin.full_name or "").strip() or st.admin.get_full_name() or st.admin.email or "—"
    course = st.course.name if st.course_id else "—"
    sess = st.session.intake_label if st.session_id else "—"
    phone = (st.admin.phone_number or "").strip() or "—"
    reg = (st.student_id or "").strip() or f"id-{st.pk}"
    enr_date = format_date(st.enrollment_date) if st.enrollment_date else "—"
    try:
        bal = st.balance()
    except Exception:
        bal = 0
    if bal and bal > 0:
        fee = f"Outstanding KES {bal:,.0f}"
    else:
        fee = "Cleared"
    return [reg, name, phone, course, sess, enr_date, fee]


def group_students_for_pdf(students: list[Student], group_by: str) -> list[tuple[str, list[Student]]]:
    if group_by == "course":
        keyfn = lambda s: s.course.name if s.course_id else "— No course —"
    elif group_by == "session":
        keyfn = lambda s: s.session.intake_label if s.session_id else "— No session —"
    else:
        return [("", students)]
    students = sorted(students, key=keyfn)
    out = []
    for label, grp in groupby(students, key=keyfn):
        out.append((label, list(grp)))
    return out


def enrollment_row_cells(enrollment) -> list[str]:
    st = enrollment.student
    adm = st.admin
    name = (adm.full_name or "").strip() or adm.get_full_name() or adm.email or "—"
    reg = (st.student_id or "").strip() or f"id-{st.pk}"
    phone = (adm.phone_number or "").strip() or "—"
    course = enrollment.course.name if enrollment.course_id else "—"
    sess = enrollment.session.intake_label if enrollment.session_id else "—"
    start = format_date(enrollment.start_date) if enrollment.start_date else "—"
    stat = enrollment.get_status_display()
    try:
        bal = enrollment.balance_due
    except Exception:
        bal = 0
    fee = "Cleared" if not bal or bal <= 0 else f"Outstanding KES {int(bal):,}"
    return [reg, name, phone, course, sess, start, stat, fee]


def describe_enrollment_export_filters(request) -> str:
    from .models import Course, Session

    GET = request.GET
    parts = []
    status = (GET.get("status") or "active").strip()
    if status in ("active", "completed", "cancelled"):
        parts.append(f"Enrollment status: {status.title()}")
    elif status == "all":
        parts.append("Enrollment status: All")
    raw_course = (GET.get("course") or "").strip()
    if raw_course.isdigit():
        c = Course.objects.filter(pk=int(raw_course)).values_list("name", flat=True).first()
        if c:
            parts.append(f"Course: {c}")
    raw_session = (GET.get("session") or "").strip()
    if raw_session.isdigit():
        s = Session.objects.filter(pk=int(raw_session)).first()
        if s:
            parts.append(f"Session: {s.intake_label}")
    if not parts:
        parts.append("All enrollments (default filter on page)")
    return " · ".join(parts)


def get_enrollments_for_export_list(request) -> list:
    """Same filters as Students overview by course (one row per enrollment)."""
    from django.db.models import F, IntegerField, Sum

    from .models import Enrollment

    status = (request.GET.get("status") or "active").strip()
    if status not in ("active", "completed", "cancelled", "all"):
        status = "active"
    raw_course = (request.GET.get("course") or "").strip()
    raw_session = (request.GET.get("session") or "").strip()
    course_id = int(raw_course) if raw_course.isdigit() else None
    session_id = int(raw_session) if raw_session.isdigit() else None

    enroll_qs = (
        Enrollment.objects.select_related("student__admin", "course", "session")
        .annotate(
            paid_total=Sum("payments__amount", default=0, output_field=IntegerField()),
        )
        .annotate(balance_remaining=F("total_fee") - F("paid_total"))
        .order_by(
            "course__name",
            "-session__start_year",
            "student__admin__full_name",
            "student__admin__first_name",
            "id",
        )
    )
    if status != "all":
        enroll_qs = enroll_qs.filter(status=status)
    if course_id is not None:
        enroll_qs = enroll_qs.filter(course_id=course_id)
    if session_id is not None:
        enroll_qs = enroll_qs.filter(session_id=session_id)
    return list(enroll_qs)
