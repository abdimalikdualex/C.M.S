import csv
import io
import json

from django.contrib import messages
from django.core.files.storage import FileSystemStorage
from django.db.models import Count, Q, Sum
from django.http import HttpResponse, JsonResponse
from django.shortcuts import (HttpResponseRedirect, get_object_or_404,redirect, render)
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from .forms import *
from .models import *
from .money import format_money
from .sms_notifications import notify_admission_confirmed

def _require_staff_role(request, allowed_roles):
    staff = get_object_or_404(Staff, admin=request.user)
    if staff.role not in allowed_roles:
        messages.error(request, "You are not allowed to access this page.")
        return None
    return staff


def _instructor_sessions(staff):
    """Relevant sessions for instructor's assigned subjects, latest first."""
    subjects = Subject.objects.filter(staff=staff).values_list("course_id", flat=True)
    qs = Session.objects.filter(enrollments__course_id__in=subjects).distinct().latest_first()
    if qs.exists():
        return qs
    return Session.objects.active_or_latest()


def _ensure_enrollment(student, course, start_date=None, session=None):
    if not course:
        return None
    total_fee = course.total_fee_for_student()
    selected_session = session or Session.objects.active_or_latest().first()
    enrollment, created = Enrollment.objects.get_or_create(
        student=student,
        course=course,
        defaults={
            "start_date": start_date or timezone.localdate(),
            "total_fee": total_fee,
            "status": "active",
            "session": selected_session,
        },
    )
    if not created and (enrollment.total_fee != total_fee or enrollment.session_id != getattr(selected_session, "id", None)):
        enrollment.total_fee = total_fee
        enrollment.session = selected_session
        enrollment.save(update_fields=["total_fee", "session"])
    return enrollment


def admission_add_student(request):
    staff = _require_staff_role(request, allowed_roles={"admission", "finance"})
    if staff is None:
        return redirect(reverse("staff_home"))

    student_form = StudentForm(request.POST or None, request.FILES or None)
    context = {'form': student_form, 'page_title': 'Register Student (Admissions)'}
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
                enrollment = _ensure_enrollment(user.student, course, enrollment_date, session=session)
                AuditLog.objects.create(
                    action="student_registered",
                    detail=f"Student {user.student.student_id} enrolled to {course.name if course else 'N/A'} by admission desk.",
                    student=user.student,
                    user=request.user,
                )
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
                    AuditLog.objects.create(
                        action="payment_recorded",
                        detail=f"Payment {created_payment.receipt_no} amount KES {created_payment.amount} recorded.",
                        student=user.student,
                        user=request.user,
                    )
                try:
                    user.student.refresh_from_db()
                    notify_admission_confirmed(user.student)
                except Exception:
                    pass
                messages.success(request, "Student registered successfully.")
                next_action = request.POST.get("next_action", "enroll_another")
                if next_action == "print_receipt" and created_payment:
                    return redirect(reverse("payment_receipt", kwargs={"payment_id": created_payment.id}))
                if next_action == "view_profile":
                    return redirect(reverse("edit_student", kwargs={"student_id": user.student.id}))
                return redirect(reverse('admission_add_student'))
            except Exception as e:
                messages.error(request, "Could not register student: " + str(e))
        else:
            messages.error(request, "Please fulfil all requirements")

    return render(request, 'hod_template/add_student_template.html', context)


def staff_course_students(request):
    staff = get_object_or_404(Staff, admin=request.user)
    if staff.role not in ("admission", "finance"):
        messages.error(request, "You do not have access to this page.")
        return redirect(reverse("staff_home"))
    q = (request.GET.get("q") or "").strip()
    course_id = request.GET.get("course")
    only_pending = request.GET.get("pending") == "1"
    only_new_today = request.GET.get("new_today") == "1"
    students = Student.objects.select_related("admin", "course").all().order_by(
        "admin__first_name", "admin__last_name"
    )
    if q:
        students = students.filter(
            Q(admin__first_name__icontains=q)
            | Q(admin__last_name__icontains=q)
            | Q(admin__full_name__icontains=q)
            | Q(admin__phone_number__icontains=q)
            | Q(student_id__icontains=q)
            | Q(course__name__icontains=q)
        )
    if course_id:
        students = students.filter(course_id=course_id)
    if only_new_today:
        students = students.filter(enrollment_date=timezone.localdate())
    if only_pending:
        students = [s for s in students if s.balance() > 0]
    courses = Course.objects.all()
    context = {
        "page_title": "Course students",
        "students": students,
        "courses": courses,
        "search_q": q,
        "course_id": course_id or "",
        "only_pending": only_pending,
        "only_new_today": only_new_today,
    }
    return render(request, "staff_template/staff_course_students.html", context)


def staff_students_overview_by_course(request):
    staff = _require_staff_role(request, {"admission", "finance"})
    if staff is None:
        return redirect(reverse("staff_home"))
    from .student_overview import build_students_overview_context

    ctx = build_students_overview_context(request)
    return render(request, "main_app/students_overview_by_course.html", ctx)


def staff_home(request):
    staff = get_object_or_404(Staff, admin=request.user)
    if staff.role in ("admission", "finance"):
        total_students = Student.objects.count()
        course_label = "All courses"
    else:
        total_students = (
            Student.objects.filter(course=staff.course).count()
            if staff.course_id
            else 0
        )
        course_label = str(staff.course) if staff.course_id else ""
    total_leave = LeaveReportStaff.objects.filter(staff=staff).count()
    subjects = Subject.objects.filter(staff=staff)
    total_subject = subjects.count()
    attendance_list = Attendance.objects.filter(subject__in=subjects)
    total_attendance = attendance_list.count()
    attendance_list = []
    subject_list = []
    for subject in subjects:
        attendance_count = Attendance.objects.filter(subject=subject).count()
        subject_list.append(subject.name)
        attendance_list.append(attendance_count)
    context = {
        'page_title': 'Staff Panel - ' + str(staff.admin) + (f' ({course_label})' if course_label else ''),
        'total_students': total_students,
        'total_attendance': total_attendance,
        'total_leave': total_leave,
        'total_subject': total_subject,
        'subject_list': subject_list,
        'attendance_list': attendance_list
    }
    return render(request, 'staff_template/home_content.html', context)


def staff_take_attendance(request):
    staff = get_object_or_404(Staff, admin=request.user)
    subjects = Subject.objects.filter(staff_id=staff).select_related("course")
    sessions = _instructor_sessions(staff)
    context = {
        'subjects': subjects,
        'sessions': sessions,
        'page_title': 'Take Attendance'
    }

    return render(request, 'staff_template/staff_take_attendance.html', context)


def staff_my_classes(request):
    """Instructor-only class roster grouped by assigned subjects/courses."""
    staff = get_object_or_404(Staff, admin=request.user)
    if staff.role != "instructor":
        messages.error(request, "Only instructors can access classes and attendance.")
        return redirect(reverse("staff_home"))

    subjects = (
        Subject.objects.filter(staff=staff)
        .select_related("course")
        .order_by("course__name", "name")
    )
    classes = []
    for subject in subjects:
        enrollments = (
            Enrollment.objects.filter(
                course=subject.course,
                status="active",
            )
            .select_related("student__admin")
            .order_by("student__admin__full_name", "student__admin__first_name", "student__student_id")
        )
        classes.append(
            {
                "subject": subject,
                "course": subject.course,
                "students": [e.student for e in enrollments],
                "student_count": enrollments.count(),
            }
        )

    return render(
        request,
        "staff_template/staff_my_classes.html",
        {
            "page_title": "My Classes / My Students",
            "classes": classes,
        },
    )


@csrf_exempt
def get_students(request):
    subject_id = request.POST.get('subject')
    session_id = request.POST.get('session')
    try:
        subject = get_object_or_404(Subject, id=subject_id)
        session = get_object_or_404(Session, id=session_id) if session_id else None
        staff = get_object_or_404(Staff, admin=request.user)
        if subject.staff_id != staff.id:
            return HttpResponse("[]", content_type="application/json")

        enrollment_qs = Enrollment.objects.filter(
            course=subject.course,
            status="active",
        )
        if session is not None:
            enrollment_qs = enrollment_qs.filter(session=session)
        students = (
            Student.objects.filter(id__in=enrollment_qs.values_list("student_id", flat=True))
            .select_related("admin")
            .order_by("admin__full_name", "admin__first_name", "student_id")
        )
        if not students.exists() and session is not None:
            # Backward compatibility for legacy rows where Enrollment.session was not set.
            students = (
                Student.objects.filter(course_id=subject.course.id, session=session)
                .select_related("admin")
                .order_by("admin__full_name", "admin__first_name", "student_id")
            )
        student_data = []
        for student in students:
            data = {
                    "id": student.id,
                    "name": student.admin.get_full_name(),
                    }
            student_data.append(data)
        return JsonResponse(json.dumps(student_data), content_type='application/json', safe=False)
    except Exception as e:
        return e


@csrf_exempt
def save_attendance(request):
    student_data = request.POST.get('student_ids')
    date = request.POST.get('date')
    subject_id = request.POST.get('subject')
    session_id = request.POST.get('session')
    students = json.loads(student_data)
    try:
        session = get_object_or_404(Session, id=session_id)
        subject = get_object_or_404(Subject, id=subject_id)
        attendance = Attendance(session=session, subject=subject, date=date)
        attendance.save()

        for student_dict in students:
            student = get_object_or_404(Student, id=student_dict.get('id'))
            attendance_report = AttendanceReport(student=student, attendance=attendance, status=student_dict.get('status'))
            attendance_report.save()
    except Exception as e:
        return None

    return HttpResponse("OK")


def staff_update_attendance(request):
    staff = get_object_or_404(Staff, admin=request.user)
    subjects = Subject.objects.filter(staff_id=staff)
    sessions = _instructor_sessions(staff)
    context = {
        'subjects': subjects,
        'sessions': sessions,
        'page_title': 'Update Attendance'
    }

    return render(request, 'staff_template/staff_update_attendance.html', context)


@csrf_exempt
def get_student_attendance(request):
    attendance_date_id = request.POST.get('attendance_date_id')
    try:
        date = get_object_or_404(Attendance, id=attendance_date_id)
        attendance_data = AttendanceReport.objects.filter(attendance=date)
        student_data = []
        for attendance in attendance_data:
            sa = attendance.student.admin
            data = {"id": sa.id,
                    "name": sa.get_full_name(),
                    "status": attendance.status}
            student_data.append(data)
        return JsonResponse(json.dumps(student_data), content_type='application/json', safe=False)
    except Exception as e:
        return e


@csrf_exempt
def update_attendance(request):
    student_data = request.POST.get('student_ids')
    date = request.POST.get('date')
    students = json.loads(student_data)
    try:
        attendance = get_object_or_404(Attendance, id=date)

        for student_dict in students:
            student = get_object_or_404(
                Student, admin_id=student_dict.get('id'))
            attendance_report = get_object_or_404(AttendanceReport, student=student, attendance=attendance)
            attendance_report.status = student_dict.get('status')
            attendance_report.save()
    except Exception as e:
        return None

    return HttpResponse("OK")


def staff_apply_leave(request):
    form = LeaveReportStaffForm(request.POST or None)
    staff = get_object_or_404(Staff, admin_id=request.user.id)
    context = {
        'form': form,
        'leave_history': LeaveReportStaff.objects.filter(staff=staff),
        'page_title': 'Apply for Leave'
    }
    if request.method == 'POST':
        if form.is_valid():
            try:
                obj = form.save(commit=False)
                obj.staff = staff
                obj.save()
                messages.success(
                    request, "Application for leave has been submitted for review")
                return redirect(reverse('staff_apply_leave'))
            except Exception:
                messages.error(request, "Could not apply!")
        else:
            messages.error(request, "Form has errors!")
    return render(request, "staff_template/staff_apply_leave.html", context)


def staff_feedback(request):
    form = FeedbackStaffForm(request.POST or None)
    staff = get_object_or_404(Staff, admin_id=request.user.id)
    context = {
        'form': form,
        'feedbacks': FeedbackStaff.objects.filter(staff=staff),
        'page_title': 'Add Feedback'
    }
    if request.method == 'POST':
        if form.is_valid():
            try:
                obj = form.save(commit=False)
                obj.staff = staff
                obj.save()
                messages.success(request, "Feedback submitted for review")
                return redirect(reverse('staff_feedback'))
            except Exception:
                messages.error(request, "Could not Submit!")
        else:
            messages.error(request, "Form has errors!")
    return render(request, "staff_template/staff_feedback.html", context)


def staff_view_profile(request):
    staff = get_object_or_404(Staff, admin=request.user)
    form = StaffEditForm(request.POST or None, request.FILES or None,instance=staff)
    context = {'form': form, 'page_title': 'View/Update Profile'}
    if request.method == 'POST':
        try:
            if form.is_valid():
                first_name = form.cleaned_data.get('first_name')
                last_name = form.cleaned_data.get('last_name')
                password = form.cleaned_data.get('password') or None
                address = form.cleaned_data.get('address')
                gender = form.cleaned_data.get('gender')
                passport = request.FILES.get('profile_pic') or None
                admin = staff.admin
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
                staff.save()
                messages.success(request, "Profile Updated!")
                return redirect(reverse('staff_view_profile'))
            else:
                messages.error(request, "Invalid Data Provided")
                return render(request, "staff_template/staff_view_profile.html", context)
        except Exception as e:
            messages.error(
                request, "Error Occured While Updating Profile " + str(e))
            return render(request, "staff_template/staff_view_profile.html", context)

    return render(request, "staff_template/staff_view_profile.html", context)


@csrf_exempt
def staff_fcmtoken(request):
    token = request.POST.get('token')
    try:
        staff_user = get_object_or_404(CustomUser, id=request.user.id)
        staff_user.fcm_token = token
        staff_user.save()
        return HttpResponse("True")
    except Exception as e:
        return HttpResponse("False")


def staff_view_notification(request):
    staff = get_object_or_404(Staff, admin=request.user)
    notifications = NotificationStaff.objects.filter(staff=staff)
    context = {
        'notifications': notifications,
        'page_title': "View Notifications"
    }
    return render(request, "staff_template/staff_view_notification.html", context)


def staff_add_result(request):
    staff = get_object_or_404(Staff, admin=request.user)
    subjects = Subject.objects.filter(staff=staff)
    sessions = Session.objects.all()
    context = {
        'page_title': 'Result Upload',
        'subjects': subjects,
        'sessions': sessions
    }
    if request.method == 'POST':
        try:
            student_id = request.POST.get('student_list')
            subject_id = request.POST.get('subject')
            test = request.POST.get('test')
            exam = request.POST.get('exam')
            student = get_object_or_404(Student, id=student_id)
            subject = get_object_or_404(Subject, id=subject_id)
            try:
                data = StudentResult.objects.get(
                    student=student, subject=subject)
                data.exam = exam
                data.test = test
                data.save()
                messages.success(request, "Scores Updated")
            except:
                result = StudentResult(student=student, subject=subject, test=test, exam=exam)
                result.save()
                messages.success(request, "Scores Saved")
        except Exception as e:
            messages.warning(request, "Error Occured While Processing Form")
    return render(request, "staff_template/staff_add_result.html", context)


@csrf_exempt
def fetch_student_result(request):
    try:
        subject_id = request.POST.get('subject')
        student_id = request.POST.get('student')
        student = get_object_or_404(Student, id=student_id)
        subject = get_object_or_404(Subject, id=subject_id)
        result = StudentResult.objects.get(student=student, subject=subject)
        result_data = {
            'exam': result.exam,
            'test': result.test
        }
        return HttpResponse(json.dumps(result_data))
    except Exception as e:
        return HttpResponse('False')


def _finance_reports_csv():
    output = io.StringIO()
    w = csv.writer(output)
    w.writerow(["course", "enrolled_students"])
    for c in Course.objects.annotate(enrolled=Count("enrollments", distinct=True)).order_by("name"):
        w.writerow([c.name, c.enrolled])
    w.writerow([])
    w.writerow(["student_id", "name", "course", "balance_kes"])
    for s in Student.objects.select_related("course", "admin").order_by("student_id"):
        try:
            bal = format_money(s.balance())
        except Exception:
            bal = 0
        w.writerow(
            [
                s.student_id,
                s.admin.get_full_name(),
                s.course.name if s.course_id else "",
                str(bal),
            ]
        )
    resp = HttpResponse(output.getvalue(), content_type="text/csv; charset=utf-8")
    resp["Content-Disposition"] = 'attachment; filename="finance_report.csv"'
    return resp


def staff_finance_reports(request):
    staff = _require_staff_role(request, {"admission", "finance"})
    if staff is None:
        return redirect(reverse("staff_home"))
    if request.GET.get("export") == "csv":
        return _finance_reports_csv()
    courses = Course.objects.annotate(enrolled=Count("enrollments", distinct=True)).order_by("name")
    total_students = Student.objects.filter(enrollments__isnull=False).distinct().count()
    total_collected = int(Payment.objects.aggregate(t=Sum("amount"))["t"] or 0)
    total_pending = 0
    for s in Student.objects.select_related("course"):
        try:
            b = int(s.balance() or 0)
            if b and b > 0:
                total_pending += b
        except Exception:
            pass
    total_pending = int(total_pending)
    recent_payments = (
        Payment.objects.select_related("student__admin", "course", "created_by")
        .order_by("-paid_at")[:50]
    )
    context = {
        "page_title": "Finance & enrollment summary",
        "courses": courses,
        "total_students": total_students,
        "total_collected": total_collected,
        "total_pending": total_pending,
        "recent_payments": recent_payments,
    }
    return render(request, "staff_template/staff_finance_reports.html", context)


def staff_record_payment(request):
    staff = _require_staff_role(request, {"admission", "finance"})
    if staff is None:
        return redirect(reverse("staff_home"))
    form = RecordPaymentForm(request.POST or None)
    if request.method == "POST":
        if form.is_valid():
            st = form.cleaned_data["student"]
            enrollment = form.cleaned_data["enrollment"]
            payment = Payment.objects.create(
                student=st,
                course=enrollment.course,
                enrollment=enrollment,
                amount=form.cleaned_data["amount"],
                mode=form.cleaned_data["mode"],
                reference=form.cleaned_data.get("reference") or "",
                note=form.cleaned_data.get("note") or "",
                created_by=request.user,
            )
            AuditLog.objects.create(
                action="payment_recorded",
                detail=f"Payment {payment.receipt_no} amount KES {payment.amount} recorded from desk.",
                student=st,
                user=request.user,
            )
            messages.success(request, "Payment recorded.")
            return redirect(reverse("staff_record_payment"))
        messages.error(request, "Could not record payment. Please correct the form errors and try again.")
    return render(
        request,
        "staff_template/staff_record_payment.html",
        {"form": form, "page_title": "Record payment"},
    )


def admission_enroll_existing_student(request):
    staff = _require_staff_role(request, {"admission", "finance"})
    if staff is None:
        return redirect(reverse("staff_home"))
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
        enrollment = _ensure_enrollment(student, course, start_date, session=session)
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
        AuditLog.objects.create(
            action="enrollment_created",
            detail=f"Student {student.student_id} enrolled in {course.name}.",
            student=student,
            user=request.user,
        )
        messages.success(request, "Enrollment added successfully.")
        if created_payment:
            return redirect(reverse("payment_receipt", kwargs={"payment_id": created_payment.id}))
        return redirect(reverse("staff_course_students"))
    return render(
        request,
        "staff_template/staff_record_payment.html",
        {"form": form, "page_title": "Enroll existing student in another course"},
    )
