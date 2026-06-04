import json
import os
import csv
import requests
from io import StringIO

from django.conf import settings
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.core.files.base import ContentFile
from django.core.files.storage import FileSystemStorage
from django.db.models import Count, Q, Sum
from django.http import HttpResponse, JsonResponse
from django.shortcuts import (HttpResponse, HttpResponseRedirect,
                              get_object_or_404, redirect, render)
from django.templatetags.static import static
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import UpdateView

from .access import user_can_edit_assigned_course_fees
from .db_safe import safe_aggregate_sum, safe_count, safe_first, safe_list
from .audit import (
    ACTION_CREATE,
    ACTION_DELETE,
    ACTION_EXPORT,
    ACTION_UPDATE,
    MODULE_COURSES,
    MODULE_ENROLLMENT,
    MODULE_EVENTS,
    MODULE_FEES,
    MODULE_INSTRUCTORS,
    MODULE_REPORTS,
    MODULE_SESSIONS,
    MODULE_STUDENTS,
    MODULE_SUBJECTS,
    KNOWN_MODULES,
    log_audit,
)
from .datetime_display import format_dt, format_filename_ts
from .enrollment_service import ensure_enrollment as _ensure_enrollment
from .forms import *
from .money import FEE_EDIT_VALIDATION_MSG, parse_post_whole_kes
from .models import *
from .sms_notifications import notify_admission_confirmed


def admin_home(request):
    from django.db import DatabaseError

    try:
        return _admin_home_impl(request)
    except DatabaseError:
        import logging

        logging.getLogger(__name__).exception("admin_home database error")
        context = {
            "page_title": "Administrative Dashboard",
            "total_students": 0,
            "total_staff": 0,
            "total_course": 0,
            "total_subject": 0,
            "total_fees_collected": 0,
            "total_fees_pending": 0,
            "subject_list": [],
            "attendance_list": [],
            "student_attendance_present_list": [],
            "student_attendance_leave_list": [],
            "student_name_list": [],
            "student_count_list_in_subject": [],
            "course_name_list": [],
            "student_count_list_in_course": [],
            "current_active_session": None,
            "recent_audit_logs": [],
            "coursework_pending_review_count": 0,
            "dashboard_degraded": True,
        }
        messages.warning(
            request,
            "Dashboard data could not be loaded (database or migrations). "
            "Run: python manage.py migrate",
        )
        return render(request, "hod_template/home_content.html", context)


def _admin_home_impl(request):
    from django.db import DatabaseError

    total_staff = safe_count(Staff.objects.all())
    total_students = safe_count(Student.objects.all())
    subjects = Subject.objects.all()
    total_subject = safe_count(subjects)
    total_course = safe_count(Course.objects.all())
    total_fees_collected = safe_aggregate_sum(Payment.objects.all(), "amount")
    total_fees_pending = 0
    for s in safe_list(Student.objects.select_related("course").all()):
        try:
            bal = int(s.balance() or 0)
        except Exception:
            bal = 0
        if bal and bal > 0:
            total_fees_pending += bal
    attendance_list = []
    subject_list = []
    for subject in safe_list(subjects):
        attendance_count = safe_count(Attendance.objects.filter(subject=subject))
        subject_list.append(subject.name[:7])
        attendance_list.append(attendance_count)

    course_all = safe_list(Course.objects.all())
    course_name_list = []
    subject_count_list = []
    student_count_list_in_course = []

    for course in course_all:
        subject_count_list.append(safe_count(Subject.objects.filter(course_id=course.id)))
        student_count_list_in_course.append(safe_count(Student.objects.filter(course_id=course.id)))
        course_name_list.append(course.name)

    subject_all = safe_list(Subject.objects.all())
    subject_list = []
    student_count_list_in_subject = []
    for subject in subject_all:
        if not subject.course_id:
            continue
        student_count = safe_count(Student.objects.filter(course_id=subject.course_id))
        subject_list.append(subject.name)
        student_count_list_in_subject.append(student_count)

    student_attendance_present_list = []
    student_attendance_leave_list = []
    student_name_list = []

    for student in safe_list(Student.objects.select_related("admin").all()):
        attendance = safe_count(
            AttendanceReport.objects.filter(student_id=student.id, status=True)
        )
        absent = safe_count(
            AttendanceReport.objects.filter(student_id=student.id, status=False)
        )
        leave = safe_count(
            LeaveReportStudent.objects.filter(student_id=student.id, status=1)
        )
        student_attendance_present_list.append(attendance)
        student_attendance_leave_list.append(leave + absent)
        student_name_list.append(student.admin.get_full_name())

    try:
        recent_audit_logs = list(
            AuditLog.objects.select_related("user").order_by("-created_at")[:12]
        )
    except DatabaseError:
        recent_audit_logs = []

    try:
        coursework_pending_review_count = safe_count(
            Submission.objects.filter(review_status=Submission.REVIEW_SUBMITTED)
        )
    except DatabaseError:
        coursework_pending_review_count = 0

    context = {
        "page_title": "Administrative Dashboard",
        "total_students": total_students,
        "total_staff": total_staff,
        "total_course": total_course,
        "total_subject": total_subject,
        "total_fees_collected": total_fees_collected,
        "total_fees_pending": total_fees_pending,
        "subject_list": subject_list,
        "attendance_list": attendance_list,
        "student_attendance_present_list": student_attendance_present_list,
        "student_attendance_leave_list": student_attendance_leave_list,
        "student_name_list": student_name_list,
        "student_count_list_in_subject": student_count_list_in_subject,
        "course_name_list": course_name_list,
        "student_count_list_in_course": student_count_list_in_course,
        "current_active_session": safe_first(Session.objects.active()),
        "recent_audit_logs": recent_audit_logs,
        "coursework_pending_review_count": coursework_pending_review_count,
    }
    return render(request, "hod_template/home_content.html", context)


def admin_assessments(request):
    """Superadmin + Director: all assessments overview + deep links into the same tools instructors use."""
    if not _hub_superadmin(request):
        return redirect(reverse("login_page"))
    assessments = (
        Assessment.objects.select_related("course", "instructor__admin", "session")
        .annotate(
            submission_count=Count("submissions"),
            pending_review_count=Count(
                "submissions",
                filter=Q(submissions__review_status=Submission.REVIEW_SUBMITTED),
            ),
        )
        .order_by("-created_at")
    )
    return render(
        request,
        "hod_template/admin_assessments.html",
        {
            "page_title": "Assessments overview",
            "assessments": assessments,
        },
    )


def _hub_superadmin(request) -> bool:
    return str(getattr(request.user, "user_type", "") or "").strip() in ("1", "4")


def _admin_results_queryset(request):
    qs = StudentResult.objects.select_related(
        "student__admin", "subject__course", "session", "entered_by"
    ).order_by("-updated_at")
    course_id = (request.GET.get("course") or "").strip()
    if course_id.isdigit():
        qs = qs.filter(subject__course_id=int(course_id))
    subject_id = (request.GET.get("subject") or "").strip()
    if subject_id.isdigit():
        qs = qs.filter(subject_id=int(subject_id))
    session_id = (request.GET.get("session") or "").strip()
    if session_id.isdigit():
        qs = qs.filter(session_id=int(session_id))
    q = (request.GET.get("q") or "").strip()
    if q:
        qs = qs.filter(
            Q(student__student_id__icontains=q)
            | Q(student__admin__full_name__icontains=q)
            | Q(student__admin__first_name__icontains=q)
            | Q(student__admin__last_name__icontains=q)
            | Q(student__admin__email__icontains=q)
        )
    return qs


def admin_results_overview(request):
    if not _hub_superadmin(request):
        return redirect(reverse("login_page"))
    from django.core.paginator import Paginator

    qs = _admin_results_queryset(request)
    paginator = Paginator(qs, 40)
    page_obj = paginator.get_page(request.GET.get("page"))
    qp = request.GET.copy()
    qp.pop("page", None)
    query_no_page = qp.urlencode()
    subj_qs = Subject.objects.filter(is_active=True).select_related("course").order_by(
        "course__name", "sort_order", "name"
    )
    return render(
        request,
        "hod_template/admin_results_overview.html",
        {
            "page_title": "Exam results — all courses",
            "page_obj": page_obj,
            "courses": Course.objects.order_by("name"),
            "filter_subjects": subj_qs,
            "sessions": Session.objects.latest_first(),
            "query_no_page": query_no_page,
            "filters": {
                "course": (request.GET.get("course") or "").strip(),
                "subject": (request.GET.get("subject") or "").strip(),
                "session": (request.GET.get("session") or "").strip(),
                "q": (request.GET.get("q") or "").strip(),
            },
        },
    )


def admin_results_export_csv(request):
    if not _hub_superadmin(request):
        return redirect(reverse("login_page"))
    rows = list(_admin_results_queryset(request)[:8000])
    buf = StringIO()
    w = csv.writer(buf)
    w.writerow(
        [
            "Admission No",
            "Student Name",
            "Course",
            "Unit/Subject",
            "Test",
            "Exam",
            "Total",
            "Grade",
            "Session",
            "Remarks",
            "Updated",
        ]
    )
    for r in rows:
        w.writerow(
            [
                r.student.student_id,
                r.student.admin.get_full_name(),
                r.subject.course.name if r.subject.course_id else "",
                r.subject.name,
                r.test,
                r.exam,
                r.total_score(),
                r.grade,
                r.session.intake_label if r.session_id else "",
                (r.remarks or "")[:200],
                format_dt(r.updated_at),
            ]
        )
    log_audit(
        request,
        module=MODULE_REPORTS,
        activity="Exam results exported (CSV)",
        audit_action=ACTION_EXPORT,
        target_record=f"Rows: {len(rows)}",
    )
    payload = "\ufeff" + buf.getvalue()
    fn = f"exam-results-{format_filename_ts()}.csv"
    resp = HttpResponse(payload.encode("utf-8"), content_type="text/csv; charset=utf-8")
    resp["Content-Disposition"] = f'attachment; filename="{fn}"'
    return resp


def admin_results_export_pdf(request):
    if not _hub_superadmin(request):
        return redirect(reverse("login_page"))
    from .pdf_results import build_results_register_pdf

    rows = list(_admin_results_queryset(request)[:400])
    pdf_bytes = build_results_register_pdf(
        rows,
        college_name=getattr(settings, "COLLEGE_NAME", "ELEVATE DIGITAL HUB"),
        hub_tagline=getattr(settings, "HUB_TAGLINE", "ICT Hub System"),
        college_location=getattr(settings, "COLLEGE_LOCATION", ""),
        title="Exam results register",
    )
    log_audit(
        request,
        module=MODULE_REPORTS,
        activity="Exam results exported (PDF)",
        audit_action=ACTION_EXPORT,
        target_record=f"Rows: {len(rows)}",
    )
    fn = f"exam-results-{format_filename_ts()}.pdf"
    resp = HttpResponse(pdf_bytes, content_type="application/pdf")
    resp["Content-Disposition"] = f'attachment; filename="{fn}"'
    return resp


def _audit_trail_queryset(request):
    """GET filters for audit list / exports (Superadmin-only callers)."""
    qs = AuditLog.objects.all().select_related("user", "student__admin")
    uid = (request.GET.get("user") or "").strip()
    if uid.isdigit():
        qs = qs.filter(user_id=int(uid))
    mod = (request.GET.get("module") or "").strip()
    if mod:
        qs = qs.filter(module=mod)
    act = (request.GET.get("audit_action") or "").strip()
    if act:
        qs = qs.filter(audit_action=act)
    q = (request.GET.get("q") or "").strip()
    if q:
        qs = qs.filter(
            Q(activity__icontains=q)
            | Q(detail__icontains=q)
            | Q(target_record__icontains=q)
            | Q(user_name__icontains=q)
            | Q(legacy_event__icontains=q)
            | Q(module__icontains=q)
        )
    df = (request.GET.get("date_from") or "").strip()
    dt_to = (request.GET.get("date_to") or "").strip()
    if df:
        qs = qs.filter(created_at__date__gte=df)
    if dt_to:
        qs = qs.filter(created_at__date__lte=dt_to)
    return qs.order_by("-created_at")


def audit_trail_list(request):
    if not _hub_superadmin(request):
        return redirect(reverse("login_page"))
    from django.core.paginator import Paginator

    qs = _audit_trail_queryset(request)
    paginator = Paginator(qs, 50)
    page_obj = paginator.get_page(request.GET.get("page"))
    user_ids = AuditLog.objects.exclude(user__isnull=True).values_list("user_id", flat=True).distinct()[:300]
    filter_users = CustomUser.objects.filter(pk__in=user_ids).order_by("email", "full_name")
    qs = request.GET.copy()
    qs.pop("page", None)
    query_no_page = qs.urlencode()
    return render(
        request,
        "hod_template/audit_trail.html",
        {
            "page_title": "Audit trail",
            "page_obj": page_obj,
            "known_modules": KNOWN_MODULES,
            "action_choices": AuditLog.ACTION_CHOICES,
            "filter_users": filter_users,
            "query_no_page": query_no_page,
            "filters": {
                "user": (request.GET.get("user") or "").strip(),
                "module": (request.GET.get("module") or "").strip(),
                "audit_action": (request.GET.get("audit_action") or "").strip(),
                "q": (request.GET.get("q") or "").strip(),
                "date_from": (request.GET.get("date_from") or "").strip(),
                "date_to": (request.GET.get("date_to") or "").strip(),
            },
        },
    )


def _audit_filters_description(request) -> str:
    parts = []
    g = request.GET
    if g.get("user"):
        parts.append(f"User id {g.get('user')}")
    if g.get("module"):
        parts.append(f"Module {g.get('module')}")
    if g.get("audit_action"):
        parts.append(f"Action {g.get('audit_action')}")
    if g.get("q"):
        parts.append(f"Search “{g.get('q')}”")
    if g.get("date_from"):
        parts.append(f"From {g.get('date_from')}")
    if g.get("date_to"):
        parts.append(f"To {g.get('date_to')}")
    return " · ".join(parts) if parts else "No filters (all rows)"


def audit_trail_export_csv(request):
    if not _hub_superadmin(request):
        return redirect(reverse("login_page"))
    rows = list(_audit_trail_queryset(request)[:5000])
    buf = StringIO()
    w = csv.writer(buf)
    w.writerow(
        [
            "When",
            "User",
            "Role",
            "Module",
            "Action type",
            "Activity",
            "Legacy event",
            "Target",
            "Detail",
            "IP",
        ]
    )
    for r in rows:
        w.writerow(
            [
                format_dt(r.created_at, seconds=True),
                r.user_name or (r.user.email if r.user_id else ""),
                r.user_role,
                r.module,
                r.get_audit_action_display(),
                r.activity,
                r.legacy_event,
                r.target_record,
                (r.detail or "")[:500],
                r.ip_address,
            ]
        )
    log_audit(
        request,
        module=MODULE_REPORTS,
        activity="Audit trail exported (CSV)",
        audit_action=ACTION_EXPORT,
        target_record=f"Rows: {len(rows)}",
        detail=_audit_filters_description(request),
    )
    payload = "\ufeff" + buf.getvalue()
    fn = f"audit-trail-{format_filename_ts()}.csv"
    resp = HttpResponse(payload.encode("utf-8"), content_type="text/csv; charset=utf-8")
    resp["Content-Disposition"] = f'attachment; filename="{fn}"'
    return resp


def audit_trail_export_pdf(request):
    if not _hub_superadmin(request):
        return redirect(reverse("login_page"))
    from .pdf_audit_trail import build_audit_trail_pdf

    rows = list(_audit_trail_queryset(request)[:500])
    pdf_bytes = build_audit_trail_pdf(
        rows,
        college_name=getattr(settings, "COLLEGE_NAME", "ELEVATE DIGITAL HUB"),
        filters_note=_audit_filters_description(request),
    )
    log_audit(
        request,
        module=MODULE_REPORTS,
        activity="Audit trail exported (PDF)",
        audit_action=ACTION_EXPORT,
        target_record=f"Rows: {len(rows)}",
        detail=_audit_filters_description(request),
    )
    fn = f"audit-trail-{format_filename_ts()}.pdf"
    resp = HttpResponse(pdf_bytes, content_type="application/pdf")
    resp["Content-Disposition"] = f'attachment; filename="{fn}"'
    return resp


def admin_hub_events(request):
    if not _hub_superadmin(request):
        return redirect(reverse("login_page"))
    events = HubEvent.objects.annotate(reg_count=Count("registrations")).order_by(
        "-starts_at"
    )
    return render(
        request,
        "hod_template/admin_hub_events.html",
        {"page_title": "Hub events & community", "events": events},
    )


def admin_hub_event_add(request):
    if not _hub_superadmin(request):
        return redirect(reverse("login_page"))
    form = HubEventForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        ev = form.save()
        log_audit(
            request,
            module=MODULE_EVENTS,
            activity="Hub event created",
            audit_action=ACTION_CREATE,
            target_record=ev.title[:500],
        )
        messages.success(request, "Event created.")
        return redirect(reverse("admin_hub_events"))
    return render(
        request,
        "hod_template/admin_hub_event_form.html",
        {"page_title": "Add hub event", "form": form},
    )


def admin_hub_event_toggle_publish(request, event_id):
    if not _hub_superadmin(request):
        return redirect(reverse("login_page"))
    if request.method != "POST":
        return redirect(reverse("admin_hub_events"))
    ev = get_object_or_404(HubEvent, pk=event_id)
    ev.is_published = not ev.is_published
    ev.save(update_fields=["is_published", "updated_at"])
    state = "published" if ev.is_published else "unpublished"
    log_audit(
        request,
        module=MODULE_EVENTS,
        activity=f"Hub event {state}",
        audit_action=ACTION_UPDATE,
        target_record=ev.title[:500],
        detail=state,
    )
    messages.success(request, f"“{ev.title}” is now {state} on the student events page.")
    return redirect(reverse("admin_hub_events"))


def admin_export_students_pdf(request):
    """Superadmin: downloadable student register (filtered, branded PDF)."""
    if not _hub_superadmin(request):
        return redirect(reverse("login_page"))
    from .pdf_students_list import build_student_register_pdf
    from .student_export_utils import describe_export_filters, get_students_for_export_list

    students = get_students_for_export_list(request)
    gb = (request.GET.get("group_by") or "").strip()
    pdf_bytes = build_student_register_pdf(
        students,
        college_name=getattr(settings, "COLLEGE_NAME", "ELEVATE DIGITAL HUB"),
        hub_tagline=getattr(settings, "HUB_TAGLINE", "ICT Hub System"),
        college_location=getattr(settings, "COLLEGE_LOCATION", ""),
        filters_description=describe_export_filters(request),
        group_by=gb if gb in ("course", "session") else "",
    )
    fn = f"student-register-{format_filename_ts()}.pdf"
    resp = HttpResponse(pdf_bytes, content_type="application/pdf")
    resp["Content-Disposition"] = f'attachment; filename="{fn}"'
    log_audit(
        request,
        module=MODULE_REPORTS,
        activity="Student register exported (PDF)",
        audit_action=ACTION_EXPORT,
        target_record=f"Rows: {len(students)}",
        detail=describe_export_filters(request),
    )
    return resp


def admin_export_students_csv(request):
    """Superadmin: student register as UTF-8 CSV (Excel-friendly)."""
    if not _hub_superadmin(request):
        return redirect(reverse("login_page"))
    from .student_export_utils import describe_export_filters, get_students_for_export_list, student_row_cells

    students = get_students_for_export_list(request)
    buf = StringIO()
    w = csv.writer(buf)
    w.writerow(
        ["Admission No", "Full Name", "Phone", "Course", "Session", "Enrollment Date", "Fee Status"]
    )
    for st in students:
        w.writerow(student_row_cells(st))
    payload = "\ufeff" + buf.getvalue()
    fn = f"student-register-{format_filename_ts()}.csv"
    resp = HttpResponse(payload.encode("utf-8"), content_type="text/csv; charset=utf-8")
    resp["Content-Disposition"] = f'attachment; filename="{fn}"'
    log_audit(
        request,
        module=MODULE_REPORTS,
        activity="Student register exported (CSV)",
        audit_action=ACTION_EXPORT,
        target_record=f"Rows: {len(students)}",
        detail=describe_export_filters(request),
    )
    return resp


def admin_export_enrollments_pdf(request):
    """Superadmin: enrollment-level register (matches Students by course filters)."""
    if not _hub_superadmin(request):
        return redirect(reverse("login_page"))
    from .pdf_students_list import build_enrollment_register_pdf
    from .student_export_utils import describe_enrollment_export_filters, get_enrollments_for_export_list

    enrollments = get_enrollments_for_export_list(request)
    pdf_bytes = build_enrollment_register_pdf(
        enrollments,
        college_name=getattr(settings, "COLLEGE_NAME", "ELEVATE DIGITAL HUB"),
        hub_tagline=getattr(settings, "HUB_TAGLINE", "ICT Hub System"),
        college_location=getattr(settings, "COLLEGE_LOCATION", ""),
        filters_description=describe_enrollment_export_filters(request),
    )
    fn = f"enrollment-register-{format_filename_ts()}.pdf"
    resp = HttpResponse(pdf_bytes, content_type="application/pdf")
    resp["Content-Disposition"] = f'attachment; filename="{fn}"'
    log_audit(
        request,
        module=MODULE_REPORTS,
        activity="Enrollment register exported (PDF)",
        audit_action=ACTION_EXPORT,
        target_record=f"Rows: {len(enrollments)}",
        detail=describe_enrollment_export_filters(request),
    )
    return resp


def admin_export_enrollments_csv(request):
    if not _hub_superadmin(request):
        return redirect(reverse("login_page"))
    from .student_export_utils import (
        describe_enrollment_export_filters,
        enrollment_row_cells,
        get_enrollments_for_export_list,
    )

    enrollments = get_enrollments_for_export_list(request)
    buf = StringIO()
    w = csv.writer(buf)
    w.writerow(
        [
            "Admission No",
            "Full Name",
            "Phone",
            "Course",
            "Session",
            "Start Date",
            "Enrollment Status",
            "Fee Status",
        ]
    )
    for enr in enrollments:
        w.writerow(enrollment_row_cells(enr))
    payload = "\ufeff" + buf.getvalue()
    fn = f"enrollment-register-{format_filename_ts()}.csv"
    resp = HttpResponse(payload.encode("utf-8"), content_type="text/csv; charset=utf-8")
    resp["Content-Disposition"] = f'attachment; filename="{fn}"'
    log_audit(
        request,
        module=MODULE_REPORTS,
        activity="Enrollment register exported (CSV)",
        audit_action=ACTION_EXPORT,
        target_record=f"Rows: {len(enrollments)}",
        detail=describe_enrollment_export_filters(request),
    )
    return resp


def admin_mark_enrollment_complete(request, enrollment_id):
    if not _hub_superadmin(request):
        return redirect(reverse("login_page"))
    enr = get_object_or_404(Enrollment, pk=enrollment_id)
    if request.method == "POST":
        act = (request.POST.get("action") or "").strip()
        if act == "complete":
            enr.status = "completed"
            enr.completed_on = timezone.localdate()
            enr.save(update_fields=["status", "completed_on", "updated_at"])
            messages.success(
                request,
                f"Marked {enr.course.name} as completed for this learner.",
            )
            log_audit(
                request,
                module=MODULE_ENROLLMENT,
                activity="Enrollment marked completed",
                audit_action=ACTION_UPDATE,
                target_record=f"Student: {enr.student.student_id}; Course: {enr.course.name}",
                detail=f"Enrollment id {enr.pk}.",
                student=enr.student,
            )
        elif act == "reopen":
            enr.status = "active"
            enr.completed_on = None
            enr.save(update_fields=["status", "completed_on", "updated_at"])
            messages.success(request, "Enrollment reopened as active.")
            log_audit(
                request,
                module=MODULE_ENROLLMENT,
                activity="Enrollment reopened",
                audit_action=ACTION_UPDATE,
                target_record=f"Student: {enr.student.student_id}; Course: {enr.course.name}",
                detail=f"Enrollment id {enr.pk}.",
                student=enr.student,
            )
    nxt = request.POST.get("next")
    if nxt == "edit_student":
        return redirect(reverse("edit_student", kwargs={"student_id": enr.student_id}))
    return redirect(reverse("manage_student"))


def add_staff(request):
    form = StaffForm(request.POST or None, request.FILES or None)
    context = {'form': form, 'page_title': 'Add Staff'}
    if request.method == 'POST':
        if form.is_valid():
            first_name = form.cleaned_data.get('first_name')
            last_name = form.cleaned_data.get('last_name')
            address = form.cleaned_data.get('address')
            phone_number = form.cleaned_data.get('phone_number')
            email = form.cleaned_data.get('email')
            gender = form.cleaned_data.get('gender')
            password = form.cleaned_data.get('password')
            course = form.cleaned_data.get('course')
            passport = request.FILES.get('profile_pic')
            fs = FileSystemStorage()
            filename = fs.save(passport.name, passport)
            passport_url = fs.url(filename)
            try:
                if not email:
                    email = f"{phone_number}@walkin.local"
                user = CustomUser.objects.create_user(
                    email=email,
                    password=password,
                    user_type=2,
                    first_name=first_name,
                    last_name=last_name,
                    profile_pic=passport_url,
                    phone_number=phone_number,
                )
                user.gender = gender
                user.address = address
                user.full_name = f"{first_name} {last_name}".strip()
                role = form.cleaned_data.get("role") or "instructor"
                user.staff.role = role
                user.staff.course = course
                user.save()
                log_audit(
                    request,
                    module=MODULE_INSTRUCTORS,
                    activity="Staff / instructor added",
                    audit_action=ACTION_CREATE,
                    target_record=user.email,
                    detail=f"Role: {role}; Course: {course}",
                )
                messages.success(request, "Successfully Added")
                return redirect(reverse('add_staff'))

            except Exception as e:
                messages.error(request, "Could Not Add " + str(e))
        else:
            messages.error(request, "Please fulfil all requirements")

    return render(request, 'hod_template/add_staff_template.html', context)


def add_student(request):
    student_form = StudentForm(request.POST or None, request.FILES or None)
    context = {'form': student_form, 'page_title': 'Add Student'}
    if request.method == 'POST':
        if student_form.is_valid():
            creds = walk_in_student_user_defaults(student_form.cleaned_data)
            first_name = creds["first_name"]
            last_name = creds["last_name"]
            address = creds["address"]
            phone_number = creds["phone_number"]
            email = creds["email"]
            gender = creds["gender"]
            password = creds["password"]
            course = student_form.cleaned_data.get('course')
            session = student_form.cleaned_data.get('session')
            enrollment_date = student_form.cleaned_data.get("enrollment_date")
            pay_amount = student_form.cleaned_data.get('pay_amount') or 0
            pay_mode = student_form.cleaned_data.get('pay_mode') or 'cash'
            pay_reference = student_form.cleaned_data.get('pay_reference') or ''
            pay_note = student_form.cleaned_data.get('pay_note') or ''
            passport = request.FILES.get('profile_pic')
            passport_url = "/static/dist/img/user2-160x160.jpg"
            if passport:
                fs = FileSystemStorage()
                filename = fs.save(passport.name, passport)
                passport_url = fs.url(filename)
            try:
                user = CustomUser.objects.create_user(
                    email=email,
                    password=password,
                    user_type=3,
                    first_name=first_name,
                    last_name=last_name,
                    profile_pic=passport_url,
                    phone_number=phone_number,
                )
                user.gender = gender
                user.address = address
                user.full_name = f"{first_name} {last_name}".strip()
                user.student.session = session
                user.student.course = course
                if enrollment_date:
                    user.student.enrollment_date = enrollment_date
                user.save()
                effective_total_fee = student_form.cleaned_data.get("effective_total_fee")
                enrollment = _ensure_enrollment(
                    user.student,
                    course,
                    enrollment_date,
                    session=session,
                    total_fee_override=effective_total_fee,
                )
                log_audit(
                    request,
                    module=MODULE_STUDENTS,
                    activity="Student registered",
                    audit_action=ACTION_CREATE,
                    target_record=f"Student: {user.student.student_id}",
                    detail=(
                        f"{user.student.student_id} enrolled to "
                        f"{course.name if course else 'N/A'}."
                    ),
                    student=user.student,
                )
                # Optional: record initial payment in same flow
                created_payment = None
                if pay_amount and pay_amount > 0:
                    created_payment = Payment.objects.create(
                        student=user.student,
                        course=course,
                        enrollment=enrollment,
                        amount=pay_amount,
                        mode=pay_mode,
                        reference=pay_reference,
                        note=pay_note,
                        created_by=request.user,
                    )
                    log_audit(
                        request,
                        module=MODULE_FEES,
                        activity="Payment recorded",
                        audit_action=ACTION_CREATE,
                        target_record=f"Student: {user.student.student_id}; Receipt: {created_payment.receipt_no}",
                        detail=f"KES {created_payment.amount:,} via {created_payment.get_mode_display()}.",
                        student=user.student,
                    )
                try:
                    user.student.refresh_from_db()
                    notify_admission_confirmed(user.student)
                except Exception:
                    pass
                messages.success(request, "Successfully Added")
                next_action = request.POST.get("next_action", "enroll_another")
                if next_action == "print_receipt" and created_payment:
                    return redirect(reverse("payment_receipt", kwargs={"payment_id": created_payment.id}))
                if next_action == "view_profile":
                    return redirect(reverse("edit_student", kwargs={"student_id": user.student.id}))
                return redirect(reverse('add_student'))
            except Exception as e:
                messages.error(request, "Could Not Add: " + str(e))
        else:
            messages.error(request, "Could Not Add: ")
    return render(request, 'hod_template/add_student_template.html', context)


def admin_enroll_existing_student(request):
    initial = {}
    if request.method == "GET" and request.GET.get("lookup"):
        initial["lookup"] = request.GET.get("lookup")
    form = EnrollExistingStudentForm(request.POST or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        student = form.cleaned_data["student"]
        course = form.cleaned_data["course"]
        session = form.cleaned_data["session"]
        start_date = form.cleaned_data.get("start_date") or timezone.localdate()
        pay_amount = form.cleaned_data.get("pay_amount") or 0
        pay_mode = form.cleaned_data.get("pay_mode") or "cash"
        pay_reference = form.cleaned_data.get("pay_reference") or ""
        pay_note = form.cleaned_data.get("pay_note") or ""
        if session and student.session_id != session.id:
            student.session = session
            student.save(update_fields=["session"])
        agreed_total_fee = form.cleaned_data.get("total_fee")
        enrollment = _ensure_enrollment(
            student,
            course,
            start_date,
            session=session,
            total_fee_override=agreed_total_fee,
        )
        created_payment = None
        if pay_amount > 0:
            created_payment = Payment.objects.create(
                student=student,
                course=course,
                enrollment=enrollment,
                amount=pay_amount,
                mode=pay_mode,
                reference=pay_reference,
                note=pay_note,
                created_by=request.user,
            )
        log_audit(
            request,
            module=MODULE_ENROLLMENT,
            activity="Enrollment added",
            audit_action=ACTION_CREATE,
            target_record=f"Student: {student.student_id}; Course: {course.name}",
            detail=f"Enrolled in {course.name}.",
            student=student,
        )
        messages.success(request, "Enrollment added successfully.")
        if created_payment:
            return redirect(reverse("payment_receipt", kwargs={"payment_id": created_payment.id}))
        return redirect(reverse("manage_student"))
    return render(
        request,
        "staff_template/staff_record_payment.html",
        {"form": form, "page_title": "Enroll existing student in another course"},
    )


def add_course(request):
    form = CourseForm(request.POST or None)
    context = {
        'form': form,
        'page_title': 'Add Course'
    }
    if request.method == 'POST':
        if form.is_valid():
            try:
                c = form.save()
                log_audit(
                    request,
                    module=MODULE_COURSES,
                    activity="Course created",
                    audit_action=ACTION_CREATE,
                    target_record=c.name,
                )
                messages.success(request, "Successfully Added")
                return redirect(reverse('add_course'))
            except:
                messages.error(request, "Could Not Add")
        else:
            messages.error(request, "Could Not Add")
    return render(request, 'hod_template/add_course_template.html', context)


def add_subject(request):
    form = SubjectForm(request.POST or None)
    context = {
        'form': form,
        'page_title': 'Add Course Unit / Subject'
    }
    if request.method == 'POST':
        if form.is_valid():
            try:
                subject = form.save()
                log_audit(
                    request,
                    module=MODULE_SUBJECTS,
                    activity="Subject created",
                    audit_action=ACTION_CREATE,
                    target_record=f"{subject.name} ({subject.course.name if subject.course_id else ''})",
                )
                messages.success(request, "Successfully Added")
                return redirect(reverse('add_subject'))

            except Exception as e:
                messages.error(request, "Could Not Add " + str(e))
        else:
            messages.error(request, "Fill Form Properly")

    return render(request, 'hod_template/add_subject_template.html', context)


def manage_staff(request):
    allStaff = Staff.objects.select_related("admin", "course").order_by(
        "admin__full_name", "admin__first_name", "admin__last_name"
    )
    context = {
        'allStaff': allStaff,
        'page_title': 'Manage Staff'
    }
    return render(request, "hod_template/manage_staff.html", context)


def manage_student(request):
    q = (request.GET.get("q") or "").strip()
    only_pending = request.GET.get("pending") == "1"
    only_new_today = request.GET.get("new_today") == "1"
    raw_session = (request.GET.get("session") or "").strip()
    session_id = int(raw_session) if raw_session.isdigit() else None
    raw_course = (request.GET.get("course") or "").strip()
    course_id = int(raw_course) if raw_course.isdigit() else None
    raw_enrollment_status = (request.GET.get("enrollment_status") or "").strip()
    students = CustomUser.objects.filter(user_type=3)
    if q:
        students = students.filter(
            Q(first_name__icontains=q)
            | Q(last_name__icontains=q)
            | Q(full_name__icontains=q)
            | Q(phone_number__icontains=q)
            | Q(student__student_id__icontains=q)
            | Q(student__course__name__icontains=q)
        )
    if session_id is not None:
        students = students.filter(student__session_id=session_id)
    if course_id is not None:
        students = students.filter(student__course_id=course_id)
    if raw_enrollment_status in ("active", "completed", "cancelled"):
        students = students.filter(student__enrollments__status=raw_enrollment_status).distinct()
    if only_new_today:
        students = students.filter(student__enrollment_date=timezone.localdate())
    if only_pending:
        students = [s for s in students if s.student.balance() > 0]
    context = {
        'students': students,
        'page_title': 'Manage Students',
        'search_q': q,
        'only_pending': only_pending,
        'only_new_today': only_new_today,
        'filter_session_id': raw_session,
        'filter_course_id': raw_course,
        'filter_enrollment_status': raw_enrollment_status,
        'all_sessions': Session.objects.latest_first(),
        'all_courses': Course.objects.all().order_by("name"),
    }
    return render(request, "hod_template/manage_student.html", context)


def admin_students_overview_by_course(request):
    from .student_overview import build_students_overview_context

    ctx = build_students_overview_context(request)
    return render(request, "main_app/students_overview_by_course.html", ctx)


def manage_course(request):
    courses = Course.objects.all()
    context = {
        'courses': courses,
        'page_title': 'Manage Courses'
    }
    return render(request, "hod_template/manage_course.html", context)


def manage_subject(request):
    subjects = Subject.objects.select_related("staff__admin", "course", "session").order_by(
        "course__name", "sort_order", "name"
    )
    context = {
        'subjects': subjects,
        'page_title': 'Manage Course Units / Subjects'
    }
    return render(request, "hod_template/manage_subject.html", context)


def edit_staff(request, staff_id):
    staff = get_object_or_404(Staff, id=staff_id)
    form = StaffForm(request.POST or None, request.FILES or None, instance=staff)
    context = {
        'form': form,
        'staff_id': staff_id,
        'page_title': 'Edit Staff'
    }
    if request.method == 'POST':
        if form.is_valid():
            first_name = form.cleaned_data.get('first_name')
            last_name = form.cleaned_data.get('last_name')
            address = form.cleaned_data.get('address')
            email = form.cleaned_data.get('email')
            gender = form.cleaned_data.get('gender')
            password = form.cleaned_data.get('password') or None
            course = form.cleaned_data.get('course')
            role = form.cleaned_data.get('role')
            passport = request.FILES.get('profile_pic') or None
            try:
                user = CustomUser.objects.get(id=staff.admin.id)
                user.email = email
                if password != None:
                    user.set_password(password)
                if passport != None:
                    fs = FileSystemStorage()
                    filename = fs.save(passport.name, passport)
                    passport_url = fs.url(filename)
                    user.profile_pic = passport_url
                user.first_name = first_name
                user.last_name = last_name
                user.full_name = f"{first_name} {last_name}".strip()
                user.gender = gender
                user.address = address
                staff.course = course
                if role:
                    staff.role = role
                staff.save()
                user.save()
                log_audit(
                    request,
                    module=MODULE_INSTRUCTORS,
                    activity="Staff updated",
                    audit_action=ACTION_UPDATE,
                    target_record=user.email,
                    detail=f"Role: {role or staff.role}",
                )
                messages.success(request, "Successfully Updated")
            except Exception as e:
                messages.error(request, "Could Not Update " + str(e))
        else:
            messages.error(request, "Please fil form properly")
    return render(request, "hod_template/edit_staff_template.html", context)


def edit_student(request, student_id):
    student = get_object_or_404(Student, id=student_id)
    form = StudentForm(request.POST or None, instance=student)
    enrollments = (
        student.enrollments.select_related("course", "session").order_by("-start_date", "-id")
    )
    context = {
        'form': form,
        'student_id': student_id,
        'page_title': 'Edit Student',
        'enrollments': enrollments,
        'can_edit_enrollment_fees': user_can_edit_assigned_course_fees(request.user),
        'learner': student,
    }
    if request.method == 'POST':
        if form.is_valid():
            first_name = form.cleaned_data.get('first_name')
            last_name = form.cleaned_data.get('last_name')
            address = form.cleaned_data.get('address')
            username = form.cleaned_data.get('username')
            email = form.cleaned_data.get('email')
            gender = form.cleaned_data.get('gender')
            password = form.cleaned_data.get('password') or None
            course = form.cleaned_data.get('course')
            session = form.cleaned_data.get('session')
            passport = request.FILES.get('profile_pic') or None
            try:
                user = CustomUser.objects.get(id=student.admin.id)
                if passport != None:
                    fs = FileSystemStorage()
                    filename = fs.save(passport.name, passport)
                    passport_url = fs.url(filename)
                    user.profile_pic = passport_url
                user.username = username
                user.email = email
                if password != None:
                    user.set_password(password)
                user.first_name = first_name
                user.last_name = last_name
                user.full_name = f"{first_name} {last_name}".strip()
                student.session = session
                user.gender = gender
                user.address = address
                student.course = course
                user.save()
                student.save()
                log_audit(
                    request,
                    module=MODULE_STUDENTS,
                    activity="Student profile updated",
                    audit_action=ACTION_UPDATE,
                    target_record=f"Student: {student.student_id}",
                    student=student,
                )
                messages.success(request, "Successfully Updated")
            except Exception as e:
                messages.error(request, "Could Not Update " + str(e))
        else:
            messages.error(request, "Please Fill Form Properly!")
    return render(request, "hod_template/edit_student_template.html", context)


def _redirect_after_enrollment_fee_edit(request, student_id):
    nxt = (request.POST.get("next") or "").strip()
    if nxt == "fee_statement":
        return redirect(reverse("student_fee_statement", args=[student_id]))
    return redirect(reverse("edit_student", kwargs={"student_id": student_id}))


def edit_enrollment_fee(request, enrollment_id):
    """Superadmin only: correct agreed enrollment fee; payments unchanged; audit logged."""
    enrollment = get_object_or_404(
        Enrollment.objects.select_related("student", "course"), id=enrollment_id
    )
    student_id = enrollment.student_id
    if request.method != "POST":
        return redirect(reverse("edit_student", kwargs={"student_id": student_id}))
    if not user_can_edit_assigned_course_fees(request.user):
        raise PermissionDenied
    raw = (request.POST.get("total_fee") or "").strip()
    try:
        new_fee = parse_post_whole_kes(raw)
    except ValueError:
        messages.error(request, FEE_EDIT_VALIDATION_MSG)
        return _redirect_after_enrollment_fee_edit(request, student_id)
    paid = int(enrollment.amount_paid or 0)
    if new_fee < paid:
        messages.error(
            request,
            f"Agreed total fee ({new_fee}) cannot be less than what has already been paid ({paid}).",
        )
        return _redirect_after_enrollment_fee_edit(request, student_id)
    old_fee = int(enrollment.total_fee or 0)
    if new_fee == old_fee:
        messages.info(request, "No change; agreed total fee is already that value.")
        return _redirect_after_enrollment_fee_edit(request, student_id)
    enrollment.total_fee = new_fee
    enrollment.save(update_fields=["total_fee"])
    EnrollmentFeeAudit.objects.create(
        enrollment=enrollment,
        previous_fee=old_fee,
        new_fee=new_fee,
        edited_by=request.user,
    )
    log_audit(
        request,
        module=MODULE_FEES,
        activity="Enrollment agreed fee updated",
        audit_action=ACTION_UPDATE,
        target_record=f"Student: {enrollment.student.student_id}; Course: {enrollment.course.name if enrollment.course else ''}",
        detail=(
            f"Agreed total fee changed from KES {old_fee:,} to KES {new_fee:,}."
        ),
        student=enrollment.student,
    )
    messages.success(
        request,
        "Assigned fee updated. Balance is the updated fee minus payments already on file.",
    )
    return _redirect_after_enrollment_fee_edit(request, student_id)


def edit_course(request, course_id):
    instance = get_object_or_404(Course, id=course_id)
    form = CourseForm(request.POST or None, instance=instance)
    context = {
        'form': form,
        'course_id': course_id,
        'page_title': 'Edit Course'
    }
    if request.method == 'POST':
        if form.is_valid():
            try:
                c = form.save()
                log_audit(
                    request,
                    module=MODULE_COURSES,
                    activity="Course updated",
                    audit_action=ACTION_UPDATE,
                    target_record=c.name,
                )
                messages.success(request, "Successfully Updated")
            except:
                messages.error(request, "Could Not Update")
        else:
            messages.error(request, "Could Not Update")

    return render(request, 'hod_template/edit_course_template.html', context)


def edit_subject(request, subject_id):
    instance = get_object_or_404(Subject, id=subject_id)
    form = SubjectForm(request.POST or None, instance=instance)
    context = {
        'form': form,
        'subject_id': subject_id,
        'page_title': 'Edit Course Unit / Subject'
    }
    if request.method == 'POST':
        if form.is_valid():
            try:
                subject = form.save()
                log_audit(
                    request,
                    module=MODULE_SUBJECTS,
                    activity="Subject updated",
                    audit_action=ACTION_UPDATE,
                    target_record=f"{subject.name} ({subject.course.name if subject.course_id else ''})",
                )
                messages.success(request, "Successfully Updated")
                return redirect(reverse('edit_subject', args=[subject_id]))
            except Exception as e:
                messages.error(request, "Could Not Add " + str(e))
        else:
            messages.error(request, "Fill Form Properly")
    return render(request, 'hod_template/edit_subject_template.html', context)


def add_session(request):
    form = SessionForm(request.POST or None)
    context = {'form': form, 'page_title': 'Add Session'}
    if request.method == 'POST':
        if form.is_valid():
            try:
                sess = form.save()
                log_audit(
                    request,
                    module=MODULE_SESSIONS,
                    activity="Session created",
                    audit_action=ACTION_CREATE,
                    target_record=sess.intake_label,
                )
                messages.success(request, "Session Created")
                return redirect(reverse('add_session'))
            except Exception as e:
                messages.error(request, 'Could Not Add ' + str(e))
        else:
            messages.error(request, 'Fill Form Properly ')
    return render(request, "hod_template/add_session_template.html", context)


def manage_session(request):
    sessions = Session.objects.latest_first()
    context = {'sessions': sessions, 'page_title': 'Manage Sessions'}
    return render(request, "hod_template/manage_session.html", context)


def set_active_session(request, session_id):
    """Mark one session active for the system. Single-active invariant enforced in Session.save()."""
    session = get_object_or_404(Session, id=session_id)
    if not session.is_active:
        session.is_active = True
        session.save(update_fields=["is_active"])
        log_audit(
            request,
            module=MODULE_SESSIONS,
            activity="Active session changed",
            audit_action=ACTION_UPDATE,
            target_record=session.intake_label,
        )
        messages.success(request, f"{session.intake_label} is now the active session.")
    else:
        messages.info(request, "This session is already active.")
    return redirect(reverse('manage_session'))


def edit_session(request, session_id):
    instance = get_object_or_404(Session, id=session_id)
    form = SessionForm(request.POST or None, instance=instance)
    context = {'form': form, 'session_id': session_id,
               'page_title': 'Edit Session'}
    if request.method == 'POST':
        if form.is_valid():
            try:
                sess = form.save()
                log_audit(
                    request,
                    module=MODULE_SESSIONS,
                    activity="Session updated",
                    audit_action=ACTION_UPDATE,
                    target_record=sess.intake_label,
                )
                messages.success(request, "Session Updated")
                return redirect(reverse('edit_session', args=[session_id]))
            except Exception as e:
                messages.error(
                    request, "Session Could Not Be Updated " + str(e))
                return render(request, "hod_template/edit_session_template.html", context)
        else:
            messages.error(request, "Invalid Form Submitted ")
            return render(request, "hod_template/edit_session_template.html", context)

    else:
        return render(request, "hod_template/edit_session_template.html", context)


@csrf_exempt
def check_email_availability(request):
    email = request.POST.get("email")
    try:
        user = CustomUser.objects.filter(email=email).exists()
        if user:
            return HttpResponse(True)
        return HttpResponse(False)
    except Exception as e:
        return HttpResponse(False)


@csrf_exempt
def student_feedback_message(request):
    if request.method != 'POST':
        feedbacks = FeedbackStudent.objects.all()
        context = {
            'feedbacks': feedbacks,
            'page_title': 'Student Feedback Messages'
        }
        return render(request, 'hod_template/student_feedback_template.html', context)
    else:
        feedback_id = request.POST.get('id')
        try:
            feedback = get_object_or_404(FeedbackStudent, id=feedback_id)
            reply = request.POST.get('reply')
            feedback.reply = reply
            feedback.save()
            return HttpResponse(True)
        except Exception as e:
            return HttpResponse(False)


@csrf_exempt
def staff_feedback_message(request):
    if request.method != 'POST':
        feedbacks = FeedbackStaff.objects.all()
        context = {
            'feedbacks': feedbacks,
            'page_title': 'Staff Feedback Messages'
        }
        return render(request, 'hod_template/staff_feedback_template.html', context)
    else:
        feedback_id = request.POST.get('id')
        try:
            feedback = get_object_or_404(FeedbackStaff, id=feedback_id)
            reply = request.POST.get('reply')
            feedback.reply = reply
            feedback.save()
            return HttpResponse(True)
        except Exception as e:
            return HttpResponse(False)


@csrf_exempt
def view_staff_leave(request):
    if request.method != 'POST':
        allLeave = LeaveReportStaff.objects.all()
        context = {
            'allLeave': allLeave,
            'page_title': 'Leave Applications From Staff'
        }
        return render(request, "hod_template/staff_leave_view.html", context)
    else:
        id = request.POST.get('id')
        status = request.POST.get('status')
        if (status == '1'):
            status = 1
        else:
            status = -1
        try:
            leave = get_object_or_404(LeaveReportStaff, id=id)
            leave.status = status
            leave.save()
            return HttpResponse(True)
        except Exception as e:
            return False


@csrf_exempt
def view_student_leave(request):
    if request.method != 'POST':
        allLeave = LeaveReportStudent.objects.all()
        context = {
            'allLeave': allLeave,
            'page_title': 'Leave Applications From Students'
        }
        return render(request, "hod_template/student_leave_view.html", context)
    else:
        id = request.POST.get('id')
        status = request.POST.get('status')
        if (status == '1'):
            status = 1
        else:
            status = -1
        try:
            leave = get_object_or_404(LeaveReportStudent, id=id)
            leave.status = status
            leave.save()
            return HttpResponse(True)
        except Exception as e:
            return False


def admin_view_attendance(request):
    subjects = Subject.objects.all()
    sessions = Session.objects.all()
    context = {
        'subjects': subjects,
        'sessions': sessions,
        'page_title': 'View Attendance'
    }

    return render(request, "hod_template/admin_view_attendance.html", context)


@csrf_exempt
def get_admin_attendance(request):
    subject_id = request.POST.get('subject')
    session_id = request.POST.get('session')
    attendance_date_id = request.POST.get('attendance_date_id')
    try:
        subject = get_object_or_404(Subject, id=subject_id)
        session = get_object_or_404(Session, id=session_id)
        attendance = get_object_or_404(
            Attendance, id=attendance_date_id, session=session)
        attendance_reports = AttendanceReport.objects.filter(
            attendance=attendance)
        json_data = []
        for report in attendance_reports:
            data = {
                "status":  str(report.status),
                "name": str(report.student)
            }
            json_data.append(data)
        return JsonResponse(json.dumps(json_data), safe=False)
    except Exception as e:
        return None


def admin_view_profile(request):
    admin = get_object_or_404(Admin, admin=request.user)
    form = AdminForm(request.POST or None, request.FILES or None,
                     instance=admin)
    context = {'form': form,
               'page_title': 'View/Edit Profile'
               }
    if request.method == 'POST':
        try:
            if form.is_valid():
                first_name = form.cleaned_data.get('first_name')
                last_name = form.cleaned_data.get('last_name')
                password = form.cleaned_data.get('password') or None
                passport = request.FILES.get('profile_pic') or None
                custom_user = admin.admin
                if password != None:
                    custom_user.set_password(password)
                if passport != None:
                    fs = FileSystemStorage()
                    filename = fs.save(passport.name, passport)
                    passport_url = fs.url(filename)
                    custom_user.profile_pic = passport_url
                custom_user.first_name = first_name
                custom_user.last_name = last_name
                custom_user.save()
                messages.success(request, "Profile Updated!")
                return redirect(reverse('admin_view_profile'))
            else:
                messages.error(request, "Invalid Data Provided")
        except Exception as e:
            messages.error(
                request, "Error Occured While Updating Profile " + str(e))
    return render(request, "hod_template/admin_view_profile.html", context)


def admin_notify_staff(request):
    staff = CustomUser.objects.filter(user_type=2)
    context = {
        'page_title': "Send Notifications To Staff",
        'allStaff': staff
    }
    return render(request, "hod_template/staff_notification.html", context)


def admin_notify_student(request):
    student = CustomUser.objects.filter(user_type=3)
    context = {
        'page_title': "Send Notifications To Students",
        'students': student
    }
    return render(request, "hod_template/student_notification.html", context)


@csrf_exempt
def send_student_notification(request):
    id = request.POST.get('id')
    message = request.POST.get('message')
    student = get_object_or_404(Student, admin_id=id)
    try:
        url = "https://fcm.googleapis.com/fcm/send"
        body = {
            'notification': {
                'title': "Student Management System",
                'body': message,
                'click_action': reverse('student_view_notification'),
                'icon': static('dist/img/AdminLTELogo.png')
            },
            'to': student.admin.fcm_token
        }
        headers = {'Authorization':
                   'key=AAAA3Bm8j_M:APA91bElZlOLetwV696SoEtgzpJr2qbxBfxVBfDWFiopBWzfCfzQp2nRyC7_A2mlukZEHV4g1AmyC6P_HonvSkY2YyliKt5tT3fe_1lrKod2Daigzhb2xnYQMxUWjCAIQcUexAMPZePB',
                   'Content-Type': 'application/json'}
        data = requests.post(url, data=json.dumps(body), headers=headers)
        notification = NotificationStudent(student=student, message=message)
        notification.save()
        return HttpResponse("True")
    except Exception as e:
        return HttpResponse("False")


@csrf_exempt
def send_staff_notification(request):
    id = request.POST.get('id')
    message = request.POST.get('message')
    staff = get_object_or_404(Staff, admin_id=id)
    try:
        url = "https://fcm.googleapis.com/fcm/send"
        body = {
            'notification': {
                'title': "Student Management System",
                'body': message,
                'click_action': reverse('staff_view_notification'),
                'icon': static('dist/img/AdminLTELogo.png')
            },
            'to': staff.admin.fcm_token
        }
        headers = {'Authorization':
                   'key=AAAA3Bm8j_M:APA91bElZlOLetwV696SoEtgzpJr2qbxBfxVBfDWFiopBWzfCfzQp2nRyC7_A2mlukZEHV4g1AmyC6P_HonvSkY2YyliKt5tT3fe_1lrKod2Daigzhb2xnYQMxUWjCAIQcUexAMPZePB',
                   'Content-Type': 'application/json'}
        data = requests.post(url, data=json.dumps(body), headers=headers)
        notification = NotificationStaff(staff=staff, message=message)
        notification.save()
        return HttpResponse("True")
    except Exception as e:
        return HttpResponse("False")


def delete_staff(request, staff_id):
    staff = get_object_or_404(CustomUser, staff__id=staff_id)
    label = staff.email
    staff.delete()
    log_audit(
        request,
        module=MODULE_INSTRUCTORS,
        activity="Staff deleted",
        audit_action=ACTION_DELETE,
        target_record=label,
    )
    messages.success(request, "Staff deleted successfully!")
    return redirect(reverse('manage_staff'))


def delete_student(request, student_id):
    cust = get_object_or_404(CustomUser, student__id=student_id)
    adm = cust.student.student_id
    cust.delete()
    log_audit(
        request,
        module=MODULE_STUDENTS,
        activity="Student deleted",
        audit_action=ACTION_DELETE,
        target_record=f"Student: {adm}",
    )
    messages.success(request, "Student deleted successfully!")
    return redirect(reverse('manage_student'))


def delete_course(request, course_id):
    course = get_object_or_404(Course, id=course_id)
    name = course.name
    try:
        course.delete()
        log_audit(
            request,
            module=MODULE_COURSES,
            activity="Course deleted",
            audit_action=ACTION_DELETE,
            target_record=name,
        )
        messages.success(request, "Course deleted successfully!")
    except Exception:
        messages.error(
            request, "Sorry, some students are assigned to this course already. Kindly change the affected student course and try again")
    return redirect(reverse('manage_course'))


def delete_subject(request, subject_id):
    subject = get_object_or_404(Subject, id=subject_id)
    label = f"{subject.name} ({subject.course.name if subject.course_id else ''})"
    subject.delete()
    log_audit(
        request,
        module=MODULE_SUBJECTS,
        activity="Subject deleted",
        audit_action=ACTION_DELETE,
        target_record=label,
    )
    messages.success(request, "Subject deleted successfully!")
    return redirect(reverse('manage_subject'))


def delete_session(request, session_id):
    session = get_object_or_404(Session, id=session_id)
    label = session.intake_label
    try:
        session.delete()
        log_audit(
            request,
            module=MODULE_SESSIONS,
            activity="Session deleted",
            audit_action=ACTION_DELETE,
            target_record=label,
        )
        messages.success(request, "Session deleted successfully!")
    except Exception:
        messages.error(
            request, "There are students assigned to this session. Please move them to another session.")
    return redirect(reverse('manage_session'))


def _hod_superadmin_required(request):
    """Auth + Superadmin or Director (legacy) — used for retired-role bounce pages."""
    if not request.user.is_authenticated:
        return False
    return _hub_superadmin(request)


def _default_profile_image_file():
    path = os.path.join(
        settings.BASE_DIR, "main_app", "static", "dist", "img", "AdminLTELogo.png"
    )
    with open(path, "rb") as f:
        return ContentFile(f.read(), name="default_staff_avatar.png")


# ---------------------------------------------------------------------------
# Retired roles (ICT Hub edition)
#
# Admission Officer / Finance Officer / Director are no longer supported in
# the simplified ICT Hub. Their URL routes still resolve so any legacy link
# or bookmark continues to respond, but every endpoint now flashes a notice
# and bounces back to the Superadmin home. The templates and forms remain
# on disk for reference but are unreachable from the UI.
# ---------------------------------------------------------------------------
_RETIRED_NOTICE = (
    "This role has been retired in the ICT Hub edition. "
    "Admissions, finance and oversight tasks are now owned by the Superadmin."
)


def _retired_role_redirect(request):
    if not _hod_superadmin_required(request):
        return redirect(reverse("login_page"))
    messages.info(request, _RETIRED_NOTICE)
    return redirect(reverse("admin_home"))


def manage_admission_officers(request):
    return _retired_role_redirect(request)


def add_admission_officer(request):
    return _retired_role_redirect(request)


def edit_admission_officer(request, staff_id):
    return _retired_role_redirect(request)


def toggle_admission_officer_active(request, staff_id):
    return _retired_role_redirect(request)


def soft_delete_admission_officer(request, staff_id):
    return _retired_role_redirect(request)


def manage_directors(request):
    return _retired_role_redirect(request)


def add_director(request):
    return _retired_role_redirect(request)


def toggle_director_active(request, director_id):
    return _retired_role_redirect(request)
