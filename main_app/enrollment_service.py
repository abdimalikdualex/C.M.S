"""
Single source of truth for enrollment lifecycle helpers.

Both the HOD/admin and staff/admission desks use the same logic to create
or fetch an Enrollment row. Keeping this in one module prevents the fee /
session-sync drift that previously caused manually agreed fees to be
silently overwritten on re-save.
"""
from django.utils import timezone

from .models import Enrollment, Session
from .money import quantize_kes


def ensure_enrollment(student, course, start_date=None, session=None, total_fee_override=None):
    """
    Create the (student, course) Enrollment if missing; never overwrite a fee
    that has already been written on disk.

    - On creation: total_fee = total_fee_override (if provided) else
      course.total_fee_for_student(). Session = explicit session arg, else the
      student's session, else the active session.
    - On re-save (already exists): only sync the session FK if it is missing.
      Never touch total_fee — that value belongs to the finance team.
    """
    if not course:
        return None

    selected_session = session
    if selected_session is None and getattr(student, "session_id", None):
        selected_session = student.session
    if selected_session is None:
        selected_session = Session.objects.active_or_latest().first()

    if total_fee_override is not None:
        creation_fee = quantize_kes(total_fee_override)
    else:
        creation_fee = quantize_kes(course.total_fee_for_student())

    enrollment, created = Enrollment.objects.get_or_create(
        student=student,
        course=course,
        defaults={
            "start_date": start_date or timezone.localdate(),
            "total_fee": creation_fee,
            "status": "active",
            "session": selected_session,
        },
    )

    if not created and enrollment.session_id is None and selected_session is not None:
        enrollment.session = selected_session
        enrollment.save(update_fields=["session"])

    return enrollment
