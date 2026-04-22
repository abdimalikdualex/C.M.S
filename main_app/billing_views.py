"""
Printable payment receipts and fee statements (invoice-style). No PDF dependency.
"""
from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, render

from .models import Enrollment, Payment, Staff, Student


def _is_hod(user) -> bool:
    return str(getattr(user, "user_type", "") or "").strip() == "1"


def _is_finance_or_admission_staff(user) -> bool:
    if str(getattr(user, "user_type", "") or "").strip() != "2":
        return False
    try:
        st = Staff.objects.get(admin=user)
        return st.role in ("finance", "admission")
    except Staff.DoesNotExist:
        return False


def _can_view_student_fees(user, student: Student) -> bool:
    if _is_hod(user):
        return True
    if _is_finance_or_admission_staff(user):
        return True
    if str(getattr(user, "user_type", "") or "").strip() == "3":
        return student.admin_id == user.id
    return False


def payment_receipt(request, payment_id):
    payment = get_object_or_404(
        Payment.objects.select_related("student__admin", "course", "created_by", "enrollment__course"),
        pk=payment_id,
    )
    if not _can_view_student_fees(request.user, payment.student):
        raise PermissionDenied
    ctx = _branding()
    ctx.update(
        {
            "payment": payment,
            "student": payment.student,
        }
    )
    return render(request, "main_app/payment_receipt.html", ctx)


def student_fee_statement(request, student_id):
    student = get_object_or_404(
        Student.objects.select_related("admin", "course", "session"),
        pk=student_id,
    )
    if not _can_view_student_fees(request.user, student):
        raise PermissionDenied
    return _render_fee_statement(request, student)


def my_fee_statement(request):
    """Student-only shortcut; resolves learner from the logged-in user."""
    if str(getattr(request.user, "user_type", "") or "").strip() != "3":
        raise PermissionDenied
    student = get_object_or_404(Student, admin=request.user)
    return _render_fee_statement(request, student)


def _branding():
    return {
        "college_name": getattr(settings, "COLLEGE_NAME", "ELEVATE COLLEGE"),
        "college_location": getattr(settings, "COLLEGE_LOCATION", ""),
    }


def _render_fee_statement(request, student: Student):
    payments = (
        Payment.objects.filter(student=student)
        .select_related("course", "created_by", "enrollment__course")
        .order_by("-paid_at", "-id")
    )
    enrollments = Enrollment.objects.filter(student=student).select_related("course").order_by("-start_date", "-id")
    try:
        total_due = student.total_fee()
        paid = student.total_paid()
        balance = student.balance()
    except Exception:
        total_due = paid = balance = 0
    ctx = _branding()
    ctx.update(
        {
            "student": student,
            "payments": payments,
            "enrollments": enrollments,
            "total_due": total_due,
            "total_paid": paid,
            "balance": balance,
        }
    )
    return render(request, "main_app/fee_statement.html", ctx)
