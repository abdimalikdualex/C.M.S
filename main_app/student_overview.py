"""
Students grouped by course → session → enrollments. Used by admin + admission/finance.
"""
from collections import OrderedDict

from django.db.models import F, IntegerField, Sum

from .models import Course, Enrollment, Session


def build_students_overview_context(request):
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
            "-session__id",
            "student__admin__first_name",
            "student__admin__last_name",
            "student__admin__full_name",
            "id",
        )
    )
    if status != "all":
        enroll_qs = enroll_qs.filter(status=status)
    if course_id is not None:
        enroll_qs = enroll_qs.filter(course_id=course_id)
    if session_id is not None:
        enroll_qs = enroll_qs.filter(session_id=session_id)

    # Two-level grouping: course -> session -> enrollments. Built in Python so we
    # can compute per-group totals once and skip empty courses/sessions cleanly.
    grouped = OrderedDict()
    for enrollment in enroll_qs:
        course = enrollment.course
        course_key = course.pk if course else None
        if course_key not in grouped:
            grouped[course_key] = {
                "course": course,
                "sessions": OrderedDict(),
                "student_count": 0,
                "outstanding_total": 0,
                "paid_total": 0,
            }
        course_bucket = grouped[course_key]
        sess = enrollment.session
        sess_key = sess.pk if sess else None
        if sess_key not in course_bucket["sessions"]:
            course_bucket["sessions"][sess_key] = {
                "session": sess,
                "enrollments": [],
                "student_count": 0,
                "outstanding_total": 0,
                "paid_total": 0,
            }
        sess_bucket = course_bucket["sessions"][sess_key]
        sess_bucket["enrollments"].append(enrollment)
        sess_bucket["student_count"] += 1
        sess_bucket["paid_total"] += int(enrollment.paid_total or 0)
        sess_bucket["outstanding_total"] += max(int(enrollment.balance_remaining or 0), 0)
        course_bucket["student_count"] += 1
        course_bucket["paid_total"] += int(enrollment.paid_total or 0)
        course_bucket["outstanding_total"] += max(int(enrollment.balance_remaining or 0), 0)

    course_groups = []
    for bucket in grouped.values():
        bucket["sessions"] = list(bucket["sessions"].values())
        course_groups.append(bucket)

    return {
        "page_title": "Students overview by course",
        "course_groups": course_groups,
        "filter_status": status,
        "filter_course_id": raw_course,
        "filter_session_id": raw_session,
        "all_courses": Course.objects.all().order_by("name"),
        "all_sessions": Session.objects.latest_first(),
    }
