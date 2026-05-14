import json
import math
from datetime import datetime

from django.contrib import messages
from django.utils import timezone
from django.core.files.storage import FileSystemStorage
from django.http import HttpResponse, JsonResponse
from django.shortcuts import (HttpResponseRedirect, get_object_or_404,
                              redirect, render)
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt

from .forms import *
from .models import *
from .audit import ACTION_CREATE, MODULE_ASSIGNMENTS, log_audit
from .datetime_display import format_receipt_day_stamp


def student_home(request):
    student = get_object_or_404(Student, admin=request.user)
    try:
        fee_expected = student.total_fee()
        fee_paid = student.total_paid()
        fee_balance = student.balance()
    except Exception:
        fee_expected = fee_paid = fee_balance = 0
    total_subject = (
        Subject.objects.filter(course=student.course, is_active=True).count()
        if student.course_id
        else 0
    )
    total_attendance = AttendanceReport.objects.filter(student=student).count()
    total_present = AttendanceReport.objects.filter(student=student, status=True).count()
    if total_attendance == 0:  # Don't divide. DivisionByZero
        percent_absent = percent_present = 0
    else:
        percent_present = math.floor((total_present/total_attendance) * 100)
        percent_absent = math.ceil(100 - percent_present)
    subject_name = []
    data_present = []
    data_absent = []
    subjects = (
        Subject.objects.filter(course=student.course, is_active=True)
        if student.course_id
        else Subject.objects.none()
    )
    for subject in subjects:
        attendance = Attendance.objects.filter(subject=subject)
        present_count = AttendanceReport.objects.filter(
            attendance__in=attendance, status=True, student=student).count()
        absent_count = AttendanceReport.objects.filter(
            attendance__in=attendance, status=False, student=student).count()
        subject_name.append(subject.name)
        data_present.append(present_count)
        data_absent.append(absent_count)
    context = {
        'total_attendance': total_attendance,
        'percent_present': percent_present,
        'percent_absent': percent_absent,
        'total_subject': total_subject,
        'subjects': subjects,
        'data_present': data_present,
        'data_absent': data_absent,
        'data_name': subject_name,
        'page_title': 'Student Homepage',
        'fee_expected': fee_expected,
        'fee_paid': fee_paid,
        'fee_balance': fee_balance,
        'enrolled_course': student.course,
        'learner': student,
    }
    return render(request, 'student_template/home_content.html', context)


@ csrf_exempt
def student_view_attendance(request):
    student = get_object_or_404(Student, admin=request.user)
    if request.method != 'POST':
        if not student.course_id:
            messages.error(request, "No course assigned yet.")
            return redirect(reverse('student_home'))
        course = get_object_or_404(Course, id=student.course.id)
        context = {
            'subjects': Subject.objects.filter(course=course),
            'page_title': 'View Attendance'
        }
        return render(request, 'student_template/student_view_attendance.html', context)
    else:
        subject_id = request.POST.get('subject')
        start = request.POST.get('start_date')
        end = request.POST.get('end_date')
        try:
            subject = get_object_or_404(Subject, id=subject_id)
            start_date = datetime.strptime(start, "%Y-%m-%d")
            end_date = datetime.strptime(end, "%Y-%m-%d")
            attendance = Attendance.objects.filter(
                date__range=(start_date, end_date), subject=subject)
            attendance_reports = AttendanceReport.objects.filter(
                attendance__in=attendance, student=student)
            json_data = []
            for report in attendance_reports:
                data = {
                    "date":  str(report.attendance.date),
                    "status": report.status
                }
                json_data.append(data)
            return JsonResponse(json.dumps(json_data), safe=False)
        except Exception as e:
            return None


def student_apply_leave(request):
    form = LeaveReportStudentForm(request.POST or None)
    student = get_object_or_404(Student, admin_id=request.user.id)
    context = {
        'form': form,
        'leave_history': LeaveReportStudent.objects.filter(student=student),
        'page_title': 'Apply for leave'
    }
    if request.method == 'POST':
        if form.is_valid():
            try:
                obj = form.save(commit=False)
                obj.student = student
                obj.save()
                messages.success(
                    request, "Application for leave has been submitted for review")
                return redirect(reverse('student_apply_leave'))
            except Exception:
                messages.error(request, "Could not submit")
        else:
            messages.error(request, "Form has errors!")
    return render(request, "student_template/student_apply_leave.html", context)


def student_feedback(request):
    form = FeedbackStudentForm(request.POST or None)
    student = get_object_or_404(Student, admin_id=request.user.id)
    context = {
        'form': form,
        'feedbacks': FeedbackStudent.objects.filter(student=student),
        'page_title': 'Student Feedback'

    }
    if request.method == 'POST':
        if form.is_valid():
            try:
                obj = form.save(commit=False)
                obj.student = student
                obj.save()
                messages.success(
                    request, "Feedback submitted for review")
                return redirect(reverse('student_feedback'))
            except Exception:
                messages.error(request, "Could not Submit!")
        else:
            messages.error(request, "Form has errors!")
    return render(request, "student_template/student_feedback.html", context)


def student_view_profile(request):
    student = get_object_or_404(Student, admin=request.user)
    form = StudentEditForm(request.POST or None, request.FILES or None,
                           instance=student)
    context = {'form': form,
               'page_title': 'View/Edit Profile',
               'learner': student,
               }
    if request.method == 'POST':
        try:
            if form.is_valid():
                first_name = form.cleaned_data.get('first_name')
                last_name = form.cleaned_data.get('last_name')
                password = form.cleaned_data.get('password') or None
                address = form.cleaned_data.get('address')
                gender = form.cleaned_data.get('gender')
                passport = request.FILES.get('profile_pic') or None
                admin = student.admin
                if password != None:
                    admin.set_password(password)
                if passport != None:
                    fs = FileSystemStorage()
                    filename = fs.save(passport.name, passport)
                    passport_url = fs.url(filename)
                    admin.profile_pic = passport_url
                admin.first_name = first_name
                admin.last_name = last_name
                admin.full_name = f"{first_name} {last_name}".strip()
                admin.address = address
                admin.gender = gender
                admin.save()
                student.save()
                messages.success(request, "Profile Updated!")
                return redirect(reverse('student_view_profile'))
            else:
                messages.error(request, "Invalid Data Provided")
        except Exception as e:
            messages.error(request, "Error Occured While Updating Profile " + str(e))

    return render(request, "student_template/student_view_profile.html", context)


@csrf_exempt
def student_fcmtoken(request):
    token = request.POST.get('token')
    student_user = get_object_or_404(CustomUser, id=request.user.id)
    try:
        student_user.fcm_token = token
        student_user.save()
        return HttpResponse("True")
    except Exception as e:
        return HttpResponse("False")


def student_view_notification(request):
    student = get_object_or_404(Student, admin=request.user)
    notifications = NotificationStudent.objects.filter(student=student)
    context = {
        'notifications': notifications,
        'page_title': "View Notifications"
    }
    return render(request, "student_template/student_view_notification.html", context)


def student_view_result(request):
    student = get_object_or_404(Student, admin=request.user)
    cids = _student_enrolled_course_ids(student)
    page_title = "Exam results (by course unit)"
    if not cids:
        return render(
            request,
            "student_template/student_view_result.html",
            {
                "page_title": page_title,
                "result_rows": [],
                "no_course": True,
                "completed_units": 0,
                "pending_units": 0,
                "average_total": None,
                "learner": student,
            },
        )
    units = (
        Subject.objects.filter(course_id__in=cids, is_active=True)
        .select_related("course", "session")
        .order_by("course__name", "sort_order", "name")
    )
    unit_ids = list(units.values_list("id", flat=True))
    results_by_subject = {
        r.subject_id: r
        for r in StudentResult.objects.filter(
            student=student,
            subject_id__in=unit_ids,
        ).select_related("subject", "subject__course", "session")
    }
    result_rows = []
    totals_for_avg = []
    for u in units:
        r = results_by_subject.get(u.id)
        status_label = "Pending"
        total = None
        grade = ""
        remarks = ""
        if r is not None and (r.test or r.exam):
            status_label = "Recorded"
            total = r.total_score()
            grade = r.grade or ""
            remarks = (r.remarks or "").strip()
            totals_for_avg.append(float(total))
        result_rows.append(
            {
                "unit": u,
                "result": r,
                "total": total,
                "grade": grade,
                "remarks": remarks,
                "status_label": status_label,
            }
        )
    n = len(result_rows)
    completed_units = sum(1 for row in result_rows if row["status_label"] == "Recorded")
    pending_units = n - completed_units
    average_total = None
    if totals_for_avg:
        average_total = round(sum(totals_for_avg) / len(totals_for_avg), 1)
    return render(
        request,
        "student_template/student_view_result.html",
        {
            "page_title": page_title,
            "result_rows": result_rows,
            "no_course": False,
            "completed_units": completed_units,
            "pending_units": pending_units,
            "average_total": average_total,
            "learner": student,
        },
    )


def student_result_slip_pdf(request):
    """PDF result slip for the logged-in learner (own results only)."""
    from django.conf import settings

    student = get_object_or_404(Student, admin=request.user)
    cids = _student_enrolled_course_ids(student)
    if not cids:
        return HttpResponse("No enrolled courses.", status=404, content_type="text/plain")
    units = (
        Subject.objects.filter(course_id__in=cids, is_active=True)
        .select_related("course")
        .order_by("course__name", "sort_order", "name")
    )
    unit_ids = list(units.values_list("id", flat=True))
    results_by_subject = {
        r.subject_id: r
        for r in StudentResult.objects.filter(
            student=student,
            subject_id__in=unit_ids,
        ).select_related("subject")
    }
    result_rows = []
    for u in units:
        r = results_by_subject.get(u.id)
        if r is None or not (r.test or r.exam):
            continue
        result_rows.append(
            {
                "course_name": u.course.name if u.course_id else "",
                "unit_name": u.name,
                "test": r.test,
                "exam": r.exam,
                "total": f"{r.total_score():.1f}",
                "grade": r.grade or "",
                "remarks": (r.remarks or "")[:200],
            }
        )
    from .pdf_results import build_student_result_slip_pdf

    pdf_bytes = build_student_result_slip_pdf(
        student,
        result_rows,
        college_name=getattr(settings, "COLLEGE_NAME", "ELEVATE DIGITAL HUB"),
        hub_tagline=getattr(settings, "HUB_TAGLINE", "ICT Hub System"),
        college_location=getattr(settings, "COLLEGE_LOCATION", ""),
    )
    adm = (student.student_id or "learner").replace("/", "-")
    fn = f"result-slip-{adm}-{format_receipt_day_stamp()}.pdf"
    resp = HttpResponse(pdf_bytes, content_type="application/pdf")
    resp["Content-Disposition"] = f'inline; filename="{fn}"'
    return resp


def _student_enrolled_course_ids(student):
    ids = set()
    if student.course_id:
        ids.add(student.course_id)
    ids.update(
        student.enrollments.filter(status="active").values_list("course_id", flat=True)
    )
    return ids


def _student_can_access_assessment(student, assessment) -> bool:
    return assessment.course_id in _student_enrolled_course_ids(student)


def student_assessment_list(request):
    student = get_object_or_404(Student, admin=request.user)
    cids = _student_enrolled_course_ids(student)
    assessments = (
        Assessment.objects.filter(course_id__in=cids)
        .select_related("course", "instructor__admin")
        .order_by("-due_date")
    )
    now = timezone.now()
    rows = []
    for a in assessments:
        sub = a.submissions.filter(student=student).first()
        rows.append(
            {
                "assessment": a,
                "submission": sub,
                "late": now > a.due_date,
            }
        )
    return render(
        request,
        "student_template/student_assessments_list.html",
        {
            "page_title": "Practicals & projects",
            "rows": rows,
            "now": now,
        },
    )


def student_assessment_detail(request, pk):
    student = get_object_or_404(Student, admin=request.user)
    assessment = get_object_or_404(Assessment.objects.select_related("course"), pk=pk)
    if not _student_can_access_assessment(student, assessment):
        messages.error(request, "You are not assigned to this course.")
        return redirect(reverse("student_assessment_list"))
    submission = assessment.submissions.filter(student=student).first()
    now = timezone.now()
    closed = assessment.closes_at_deadline and now > assessment.due_date
    graded = submission and submission.grade is not None

    if request.method == "POST":
        if closed or graded:
            messages.error(request, "This assessment is no longer open for submission.")
            return redirect(reverse("student_assessment_detail", kwargs={"pk": pk}))
        text = (request.POST.get("text_answer") or "").strip()
        upload = request.FILES.get("file")
        if not text and not upload:
            messages.error(request, "Provide a written answer and/or attach a file.")
            return redirect(reverse("student_assessment_detail", kwargs={"pk": pk}))
        if submission is None:
            submission = Submission(assessment=assessment, student=student)
        submission.text_answer = text
        if upload:
            submission.file = upload
        submission.save()
        log_audit(
            request,
            module=MODULE_ASSIGNMENTS,
            activity="Assignment submission saved",
            audit_action=ACTION_CREATE,
            target_record=f"{assessment.title}: {student.student_id}",
            student=student,
        )
        messages.success(request, "Submission saved.")
        return redirect(reverse("student_assessment_detail", kwargs={"pk": pk}))

    return render(
        request,
        "student_template/student_assessment_detail.html",
        {
            "page_title": assessment.title,
            "assessment": assessment,
            "submission": submission,
            "now": now,
            "closed": closed,
            "graded": graded,
        },
    )
