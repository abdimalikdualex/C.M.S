"""
SMS queue/logging for Kenyan ops. Logs every message; optional real send via sms_placeholder.
Wire Africa's Talking / Safaricom later without changing call sites.
"""
from __future__ import annotations

import re
from typing import Optional

from django.conf import settings

from .models import SmsLog
from .money import format_money
from .sms_placeholder import send_sms


def _normalize_ke_phone(raw: str) -> str:
    phone = re.sub(r"\s+", "", (raw or "").strip())
    if not phone:
        return ""
    if phone.startswith("0") and len(phone) >= 10:
        phone = "254" + phone[1:]
    if not phone.startswith("+"):
        pass
    return phone


def log_and_send_sms(
    *,
    to_phone: str,
    message: str,
    reason: str,
    student=None,
    payment=None,
) -> Optional[SmsLog]:
    to_phone = _normalize_ke_phone(to_phone)
    if not to_phone or len(message) > 5000:
        return None
    log = SmsLog.objects.create(
        to_phone=to_phone,
        message=message[:2000],
        reason=reason,
        student=student,
        payment=payment,
        status="logged",
    )
    try:
        ok = send_sms(to_phone, message)
        log.status = "sent" if ok else "failed"
        log.save(update_fields=["status"])
    except Exception:
        log.status = "failed"
        log.save(update_fields=["status"])
    return log


def notify_payment_recorded(payment) -> None:
    """Called when a Payment row is created (see signals)."""
    st = payment.student
    phone = getattr(st.admin, "phone_number", None) or ""
    if not phone.strip():
        return
    try:
        bal = st.balance()
    except Exception:
        bal = 0
    course_name = st.course.name if st.course_id else "—"
    msg = (
        f"{getattr(settings, 'COLLEGE_NAME', 'ELEVATE COLLEGE')}: Payment KES {format_money(payment.amount)} received. "
        f"Receipt {payment.receipt_no}. Course: {course_name}. Balance KES {format_money(bal)}."
    )
    log_and_send_sms(
        to_phone=phone,
        message=msg,
        reason="payment",
        student=st,
        payment=payment,
    )


def notify_admission_confirmed(student) -> None:
    """Call after successful student registration (walk-in flow)."""
    phone = getattr(student.admin, "phone_number", None) or ""
    if not phone.strip():
        return
    name = student.admin.get_full_name()
    cid = student.course.name if student.course_id else "TBC"
    msg = (
        f"{getattr(settings, 'COLLEGE_NAME', 'ELEVATE COLLEGE')}: Hi {name}, you are enrolled in {cid}. "
        f"Student ID: {student.student_id or 'pending'}."
    )
    log_and_send_sms(
        to_phone=phone,
        message=msg,
        reason="admission",
        student=student,
        payment=None,
    )


def notify_class_reminder(student, message: str) -> Optional[SmsLog]:
    """Placeholder hook for future timetable-driven reminders."""
    phone = getattr(student.admin, "phone_number", None) or ""
    if not phone.strip():
        return None
    return log_and_send_sms(
        to_phone=phone,
        message=message,
        reason="class_reminder",
        student=student,
        payment=None,
    )
