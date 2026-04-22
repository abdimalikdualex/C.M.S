import json
import os
import requests

from django.conf import settings
from django.contrib import messages
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

from .forms import *
from .models import *
from .sms_notifications import notify_admission_confirmed


def _ensure_enrollment(student, course, start_date=None):
    if not course:
        return None
    total_fee = course.total_fee_for_student()
    selected_session = None
    if hasattr(student, "session") and student.session_id:
        selected_session = student.session
    if selected_session is None:
        selected_session = Session.objects.active_or_latest().first()
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


def admin_home(request):
    total_staff = Staff.objects.all().count()
    total_students = Student.objects.all().count()
    subjects = Subject.objects.all()
    total_subject = subjects.count()
    total_course = Course.objects.all().count()
    total_fees_collected = int(Payment.objects.all().aggregate(total=Sum("amount")).get("total") or 0)
    # Pending = sum of student balances (simple MVP)
    total_fees_pending = 0
    for s in Student.objects.select_related("course").all():
        try:
            bal = int(s.balance() or 0)
        except Exception:
            bal = 0
        if bal and bal > 0:
            total_fees_pending += bal
    total_fees_pending = int(total_fees_pending)
    attendance_list = Attendance.objects.filter(subject__in=subjects)
    total_attendance = attendance_list.count()
    attendance_list = []
    subject_list = []
    for subject in subjects:
        attendance_count = Attendance.objects.filter(subject=subject).count()
        subject_list.append(subject.name[:7])
        attendance_list.append(attendance_count)

    # Total Subjects and students in Each Course
    course_all = Course.objects.all()
    course_name_list = []
    subject_count_list = []
    student_count_list_in_course = []

    for course in course_all:
        subjects = Subject.objects.filter(course_id=course.id).count()
        students = Student.objects.filter(course_id=course.id).count()
        course_name_list.append(course.name)
        subject_count_list.append(subjects)
        student_count_list_in_course.append(students)
    
    subject_all = Subject.objects.all()
    subject_list = []
    student_count_list_in_subject = []
    for subject in subject_all:
        course = Course.objects.get(id=subject.course.id)
        student_count = Student.objects.filter(course_id=course.id).count()
        subject_list.append(subject.name)
        student_count_list_in_subject.append(student_count)


    # For Students
    student_attendance_present_list=[]
    student_attendance_leave_list=[]
    student_name_list=[]

    students = Student.objects.all()
    for student in students:
        
        attendance = AttendanceReport.objects.filter(student_id=student.id, status=True).count()
        absent = AttendanceReport.objects.filter(student_id=student.id, status=False).count()
        leave = LeaveReportStudent.objects.filter(student_id=student.id, status=1).count()
        student_attendance_present_list.append(attendance)
        student_attendance_leave_list.append(leave+absent)
        student_name_list.append(student.admin.get_full_name())

    context = {
        'page_title': "Administrative Dashboard",
        'total_students': total_students,
        'total_staff': total_staff,
        'total_course': total_course,
        'total_subject': total_subject,
        'total_fees_collected': total_fees_collected,
        'total_fees_pending': total_fees_pending,
        'subject_list': subject_list,
        'attendance_list': attendance_list,
        'student_attendance_present_list': student_attendance_present_list,
        'student_attendance_leave_list': student_attendance_leave_list,
        "student_name_list": student_name_list,
        "student_count_list_in_subject": student_count_list_in_subject,
        "student_count_list_in_course": student_count_list_in_course,
        "course_name_list": course_name_list,
        "current_active_session": Session.objects.active().first(),

    }
    return render(request, 'hod_template/home_content.html', context)


def admin_assessments(request):
    """Super Admin: all assessments and submission counts (read-only overview)."""
    if str(getattr(request.user, "user_type", "") or "").strip() != "1":
        return redirect(reverse("login_page"))
    assessments = (
        Assessment.objects.select_related("course", "instructor__admin", "session")
        .annotate(submission_count=Count("submissions"))
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
                enrollment = _ensure_enrollment(user.student, course, enrollment_date)
                AuditLog.objects.create(
                    action="student_registered",
                    detail=f"Student {user.student.student_id} enrolled to {course.name if course else 'N/A'} by admin.",
                    student=user.student,
                    user=request.user,
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
        enrollment = _ensure_enrollment(student, course, start_date)
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
                form.save()
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
        'page_title': 'Add Subject'
    }
    if request.method == 'POST':
        if form.is_valid():
            name = form.cleaned_data.get('name')
            course = form.cleaned_data.get('course')
            staff = form.cleaned_data.get('staff')
            try:
                subject = Subject()
                subject.name = name
                subject.staff = staff
                subject.course = course
                subject.save()
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
    subjects = Subject.objects.all()
    context = {
        'subjects': subjects,
        'page_title': 'Manage Subjects'
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
                messages.success(request, "Successfully Updated")
                return redirect(reverse('edit_staff', args=[staff_id]))
            except Exception as e:
                messages.error(request, "Could Not Update " + str(e))
        else:
            messages.error(request, "Please fil form properly")
    return render(request, "hod_template/edit_staff_template.html", context)


def edit_student(request, student_id):
    student = get_object_or_404(Student, id=student_id)
    form = StudentForm(request.POST or None, instance=student)
    context = {
        'form': form,
        'student_id': student_id,
        'page_title': 'Edit Student'
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
                messages.success(request, "Successfully Updated")
                return redirect(reverse('edit_student', args=[student_id]))
            except Exception as e:
                messages.error(request, "Could Not Update " + str(e))
        else:
            messages.error(request, "Please Fill Form Properly!")
    else:
        return render(request, "hod_template/edit_student_template.html", context)


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
                form.save()
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
        'page_title': 'Edit Subject'
    }
    if request.method == 'POST':
        if form.is_valid():
            name = form.cleaned_data.get('name')
            course = form.cleaned_data.get('course')
            staff = form.cleaned_data.get('staff')
            try:
                subject = Subject.objects.get(id=subject_id)
                subject.name = name
                subject.staff = staff
                subject.course = course
                subject.save()
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
                form.save()
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


def edit_session(request, session_id):
    instance = get_object_or_404(Session, id=session_id)
    form = SessionForm(request.POST or None, instance=instance)
    context = {'form': form, 'session_id': session_id,
               'page_title': 'Edit Session'}
    if request.method == 'POST':
        if form.is_valid():
            try:
                form.save()
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
    staff.delete()
    messages.success(request, "Staff deleted successfully!")
    return redirect(reverse('manage_staff'))


def delete_student(request, student_id):
    student = get_object_or_404(CustomUser, student__id=student_id)
    student.delete()
    messages.success(request, "Student deleted successfully!")
    return redirect(reverse('manage_student'))


def delete_course(request, course_id):
    course = get_object_or_404(Course, id=course_id)
    try:
        course.delete()
        messages.success(request, "Course deleted successfully!")
    except Exception:
        messages.error(
            request, "Sorry, some students are assigned to this course already. Kindly change the affected student course and try again")
    return redirect(reverse('manage_course'))


def delete_subject(request, subject_id):
    subject = get_object_or_404(Subject, id=subject_id)
    subject.delete()
    messages.success(request, "Subject deleted successfully!")
    return redirect(reverse('manage_subject'))


def delete_session(request, session_id):
    session = get_object_or_404(Session, id=session_id)
    try:
        session.delete()
        messages.success(request, "Session deleted successfully!")
    except Exception:
        messages.error(
            request, "There are students assigned to this session. Please move them to another session.")
    return redirect(reverse('manage_session'))


def _hod_superadmin_required(request):
    if not request.user.is_authenticated or str(request.user.user_type) != "1":
        return False
    return True


def _default_profile_image_file():
    path = os.path.join(
        settings.BASE_DIR, "main_app", "static", "dist", "img", "AdminLTELogo.png"
    )
    with open(path, "rb") as f:
        return ContentFile(f.read(), name="default_staff_avatar.png")


def manage_admission_officers(request):
    if not _hod_superadmin_required(request):
        return redirect(reverse("login_page"))
    q = (request.GET.get("q") or "").strip()
    status = request.GET.get("status", "all")
    qs = Staff.objects.filter(role__in=("admission", "finance"), is_deleted=False).select_related(
        "admin", "course"
    )
    if q:
        qs = qs.filter(
            Q(admin__first_name__icontains=q)
            | Q(admin__last_name__icontains=q)
            | Q(admin__full_name__icontains=q)
            | Q(admin__phone_number__icontains=q)
            | Q(admin__email__icontains=q)
        )
    if status == "active":
        qs = qs.filter(admin__is_active=True)
    elif status == "inactive":
        qs = qs.filter(admin__is_active=False)
    qs = qs.order_by("admin__full_name", "admin__first_name", "admin__last_name")
    context = {
        "page_title": "Admission Officers",
        "officers": qs,
        "search_q": q,
        "status": status,
    }
    return render(request, "hod_template/manage_admission_officers.html", context)


def add_admission_officer(request):
    if not _hod_superadmin_required(request):
        return redirect(reverse("login_page"))
    form = AdmissionOfficerCreateForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        full_name = form.cleaned_data["full_name"]
        phone = form.cleaned_data["phone_number"]
        email = (form.cleaned_data.get("email") or "").strip().lower()
        password = form.cleaned_data["password"]
        is_active = form.cleaned_data.get("is_active", True)
        if not email:
            email = f"{phone}@walkin.local"
            if CustomUser.objects.filter(email=email).exists():
                email = f"{phone}.{os.urandom(3).hex()}@walkin.local"
        try:
            user = CustomUser(
                email=email,
                user_type="2",
                full_name=full_name,
                first_name="",
                last_name="",
                phone_number=phone,
                gender="M",
                address="-",
            )
            user.set_password(password)
            user.is_active = bool(is_active)
            cf = _default_profile_image_file()
            user.profile_pic.save(cf.name, cf, save=False)
            user.save()
            user.staff.role = "admission"
            user.staff.course = None
            user.staff.is_deleted = False
            user.staff.save()
            messages.success(request, "Admission officer created.")
            return redirect(reverse("manage_admission_officers"))
        except Exception as e:
            messages.error(request, "Could not create account: " + str(e))
    context = {"page_title": "Add Admission Officer", "form": form}
    return render(request, "hod_template/add_admission_officer_template.html", context)


def edit_admission_officer(request, staff_id):
    if not _hod_superadmin_required(request):
        return redirect(reverse("login_page"))
    staff = get_object_or_404(Staff, id=staff_id, role__in=("admission", "finance"))
    form = AdmissionOfficerEditForm(request.POST or None, staff=staff)
    if request.method == "POST" and form.is_valid():
        full_name = form.cleaned_data["full_name"]
        phone = form.cleaned_data["phone_number"]
        email = (form.cleaned_data.get("email") or "").strip().lower()
        password = form.cleaned_data.get("password") or ""
        is_active = form.cleaned_data.get("is_active", True)
        if not email:
            email = f"{phone}@walkin.local"
        try:
            user = staff.admin
            user.full_name = full_name
            user.first_name = ""
            user.last_name = ""
            user.phone_number = phone
            user.email = email
            user.is_active = bool(is_active)
            if password:
                user.set_password(password)
            user.save()
            messages.success(request, "Updated successfully.")
            return redirect(reverse("manage_admission_officers"))
        except Exception as e:
            messages.error(request, "Could not update: " + str(e))
    context = {"page_title": "Edit Admission Officer", "form": form, "staff": staff}
    return render(request, "hod_template/edit_admission_officer_template.html", context)


def toggle_admission_officer_active(request, staff_id):
    if not _hod_superadmin_required(request):
        return redirect(reverse("login_page"))
    staff = get_object_or_404(Staff, id=staff_id, role__in=("admission", "finance"))
    u = staff.admin
    u.is_active = not u.is_active
    u.save()
    messages.success(
        request, "Account is now " + ("active" if u.is_active else "inactive") + "."
    )
    return redirect(reverse("manage_admission_officers"))


def soft_delete_admission_officer(request, staff_id):
    if not _hod_superadmin_required(request):
        return redirect(reverse("login_page"))
    staff = get_object_or_404(Staff, id=staff_id, role__in=("admission", "finance"))
    staff.is_deleted = True
    staff.admin.is_active = False
    staff.save()
    staff.admin.save()
    messages.success(request, "Admission officer removed from active list.")
    return redirect(reverse("manage_admission_officers"))
