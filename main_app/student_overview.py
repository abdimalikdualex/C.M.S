"""
Students grouped by course (enrollment-based). Used by admin + admission/finance.
"""
from django.db.models import F, IntegerField, Prefetch, Sum

from .models import Course, Enrollment


def build_students_overview_context(request):
    status = (request.GET.get("status") or "active").strip()
    if status not in ("active", "completed", "cancelled", "all"):
        status = "active"
    raw_course = (request.GET.get("course") or "").strip()
    course_id = None
    if raw_course.isdigit():
        course_id = int(raw_course)

    enroll_qs = (
        Enrollment.objects.select_related("student__admin")
        .annotate(
            paid_total=Sum("payments__amount", default=0, output_field=IntegerField()),
        )
        .annotate(balance_remaining=F("total_fee") - F("paid_total"))
        .order_by("student__admin__first_name", "student__admin__last_name", "student__admin__full_name", "id")
    )
    if status != "all":
        enroll_qs = enroll_qs.filter(status=status)

    courses = Course.objects.all().order_by("name")
    if course_id is not None:
        courses = courses.filter(pk=course_id)
    courses = courses.prefetch_related(Prefetch("enrollments", queryset=enroll_qs))

    return {
        "page_title": "Students overview by course",
        "courses": courses,
        "filter_status": status,
        "filter_course_id": raw_course,
        "all_courses": Course.objects.all().order_by("name"),
    }
