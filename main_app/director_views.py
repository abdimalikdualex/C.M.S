"""
Manager / Director dashboard — read-only oversight role.

Design principle (per the MVP brief):
    Director = "SEE EVERYTHING, CHANGE VERY LITTLE"

The only write capability exposed here is *not* in this module — directors are
allowed (via main_app.middleware + roles.HOD_ALLOWED_FOR_DIRECTOR) to invoke
the existing hod_views.set_active_session URL. Every view in this file is
read-only, returning either a rendered template or a CSV download.

All views are guarded by @require_director, which permits HOD (superadmin) +
Director and redirects everyone else with an explanatory flash. This is in
addition to LoginCheckMiddleWare, which already routes ut="4" users to this
module by default.
"""
import csv
import io

from django.db.models import Count, F, IntegerField, Sum
from django.http import HttpResponse
from django.shortcuts import render
from django.utils import timezone

from .models import (
    Attendance,
    AttendanceReport,
    Course,
    Enrollment,
    Payment,
    Session,
    Staff,
    Student,
)
from .money import format_money
from .roles import require_director
from .student_overview import build_students_overview_context


# ---------------------------------------------------------------------------
# Internal: shared KPI snapshot used by the dashboard and the reports page so
# both tell the same story (and we never silently drift).
# ---------------------------------------------------------------------------
def _kpi_snapshot():
    total_students = Student.objects.count()
    active_courses = Course.objects.count()
    active_sessions = Session.objects.filter(is_active=True).count()
    total_revenue = int(Payment.objects.aggregate(t=Sum("amount"))["t"] or 0)

    # Outstanding = sum of positive per-student balances.
    outstanding = 0
    for s in Student.objects.select_related("course"):
        try:
            bal = int(s.balance() or 0)
            if bal > 0:
                outstanding += bal
        except Exception:
            pass

    current_session = Session.objects.active().first()
    revenue_current_session = 0
    if current_session is not None:
        revenue_current_session = int(
            Payment.objects.filter(enrollment__session=current_session)
            .aggregate(t=Sum("amount"))["t"]
            or 0
        )

    return {
        "total_students": total_students,
        "active_courses": active_courses,
        "active_sessions": active_sessions,
        "total_revenue": total_revenue,
        "outstanding": outstanding,
        "current_session": current_session,
        "revenue_current_session": revenue_current_session,
    }


# ---------------------------------------------------------------------------
# 1. EXECUTIVE DASHBOARD
# ---------------------------------------------------------------------------
@require_director
def director_dashboard(request):
    kpis = _kpi_snapshot()
    recent_payments = (
        Payment.objects.select_related("student__admin", "course")
        .order_by("-paid_at")[:10]
    )
    context = {
        "page_title": "Executive Dashboard",
        **kpis,
        "recent_payments": recent_payments,
    }
    return render(request, "director_template/dashboard.html", context)


# ---------------------------------------------------------------------------
# 2. STUDENT OVERVIEW (read-only; reuses the existing course->session grouping)
# ---------------------------------------------------------------------------
@require_director
def director_students(request):
    ctx = build_students_overview_context(request)
    ctx["page_title"] = "Students overview"
    return render(request, "director_template/students.html", ctx)


# ---------------------------------------------------------------------------
# 3. COURSE & PROGRAM OVERVIEW
# ---------------------------------------------------------------------------
@require_director
def director_courses(request):
    courses = (
        Course.objects.annotate(
            enrolled=Count("enrollments", distinct=True),
            paid=Sum("enrollments__payments__amount", default=0, output_field=IntegerField()),
        )
        .order_by("name")
    )
    context = {
        "page_title": "Courses overview",
        "courses": courses,
    }
    return render(request, "director_template/courses.html", context)


# ---------------------------------------------------------------------------
# 4. SESSION OVERVIEW (with one allowed write: set-active via existing view)
# ---------------------------------------------------------------------------
@require_director
def director_sessions(request):
    sessions = (
        Session.objects.annotate(
            student_count=Count("student", distinct=True),
            enrollment_count=Count("enrollment", distinct=True),
        )
        .latest_first()
    )
    context = {
        "page_title": "Sessions",
        "sessions": sessions,
    }
    return render(request, "director_template/sessions.html", context)


# ---------------------------------------------------------------------------
# 5. STAFF OVERVIEW
# ---------------------------------------------------------------------------
@require_director
def director_staff(request):
    staff = (
        Staff.objects.filter(is_deleted=False)
        .select_related("admin", "course")
        .order_by("role", "admin__full_name", "admin__email")
    )
    context = {
        "page_title": "Staff overview",
        "staff_list": staff,
    }
    return render(request, "director_template/staff.html", context)


# ---------------------------------------------------------------------------
# 6. FINANCE OVERVIEW
# ---------------------------------------------------------------------------
@require_director
def director_finance(request):
    courses = (
        Course.objects.annotate(
            enrolled=Count("enrollments", distinct=True),
            collected=Sum(
                "enrollments__payments__amount", default=0, output_field=IntegerField()
            ),
            agreed=Sum("enrollments__total_fee", default=0, output_field=IntegerField()),
        )
        .annotate(outstanding=F("agreed") - F("collected"))
        .order_by("name")
    )
    sessions = (
        Session.objects.annotate(
            collected=Sum(
                "enrollment__payments__amount", default=0, output_field=IntegerField()
            ),
            agreed=Sum(
                "enrollment__total_fee", default=0, output_field=IntegerField()
            ),
        )
        .annotate(outstanding=F("agreed") - F("collected"))
        .latest_first()
    )
    recent_payments = (
        Payment.objects.select_related("student__admin", "course", "enrollment__session")
        .order_by("-paid_at")[:25]
    )
    context = {
        "page_title": "Finance overview",
        "courses": courses,
        "sessions": sessions,
        "recent_payments": recent_payments,
        **_kpi_snapshot(),
    }
    return render(request, "director_template/finance.html", context)


# ---------------------------------------------------------------------------
# 7. REPORTS — landing page + three CSV exports
# ---------------------------------------------------------------------------
@require_director
def director_reports(request):
    context = {
        "page_title": "Reports",
        **_kpi_snapshot(),
    }
    return render(request, "director_template/reports.html", context)


def _csv_response(rows, filename):
    output = io.StringIO()
    w = csv.writer(output)
    for r in rows:
        w.writerow(r)
    resp = HttpResponse(output.getvalue(), content_type="text/csv; charset=utf-8")
    resp["Content-Disposition"] = f'attachment; filename="{filename}"'
    return resp


@require_director
def director_report_students_csv(request):
    rows = [["student_id", "name", "email", "phone", "course", "session", "enrollment_date"]]
    qs = (
        Student.objects.select_related("admin", "course", "session")
        .order_by("session__start_year", "course__name", "student_id")
    )
    for s in qs:
        rows.append(
            [
                s.student_id,
                s.admin.get_full_name(),
                s.admin.email,
                s.admin.phone_number or "",
                s.course.name if s.course_id else "",
                s.session.intake_label if s.session_id else "",
                s.enrollment_date.strftime("%Y-%m-%d") if s.enrollment_date else "",
            ]
        )
    return _csv_response(rows, "students.csv")


@require_director
def director_report_finance_csv(request):
    snapshot = _kpi_snapshot()
    rows = [
        ["ELEVATE DIGITAL HUB — ICT Hub finance summary"],
        ["generated_at", timezone.now().strftime("%Y-%m-%d %H:%M")],
        ["total_students", snapshot["total_students"]],
        ["active_courses", snapshot["active_courses"]],
        ["active_sessions", snapshot["active_sessions"]],
        ["total_revenue_kes", format_money(snapshot["total_revenue"])],
        ["outstanding_kes", format_money(snapshot["outstanding"])],
        [
            "current_session",
            snapshot["current_session"].intake_label if snapshot["current_session"] else "",
        ],
        [
            "revenue_current_session_kes",
            format_money(snapshot["revenue_current_session"]),
        ],
        [],
        ["per_course_breakdown"],
        ["course", "enrolled", "agreed_fees_kes", "collected_kes", "outstanding_kes"],
    ]
    courses = (
        Course.objects.annotate(
            enrolled=Count("enrollments", distinct=True),
            collected=Sum(
                "enrollments__payments__amount", default=0, output_field=IntegerField()
            ),
            agreed=Sum("enrollments__total_fee", default=0, output_field=IntegerField()),
        )
        .order_by("name")
    )
    for c in courses:
        agreed = int(c.agreed or 0)
        collected = int(c.collected or 0)
        outstanding = max(agreed - collected, 0)
        rows.append(
            [
                c.name,
                int(c.enrolled or 0),
                format_money(agreed),
                format_money(collected),
                format_money(outstanding),
            ]
        )
    return _csv_response(rows, "finance_summary.csv")


@require_director
def director_report_attendance_csv(request):
    rows = [["student_id", "name", "course", "sessions_present", "sessions_absent", "percent_present"]]
    students = Student.objects.select_related("admin", "course").order_by("student_id")
    for s in students:
        present = AttendanceReport.objects.filter(student=s, status=True).count()
        absent = AttendanceReport.objects.filter(student=s, status=False).count()
        total = present + absent
        pct = round((present / total) * 100, 1) if total else 0.0
        rows.append(
            [
                s.student_id,
                s.admin.get_full_name(),
                s.course.name if s.course_id else "",
                present,
                absent,
                pct,
            ]
        )
    return _csv_response(rows, "attendance_summary.csv")
