from django.utils import timezone

from .models import Session, Staff, Student


def staff_role(request):
    if not request.user.is_authenticated or getattr(request.user, "user_type", None) != "2":
        return {"staff_role": None}
    try:
        return {"staff_role": Staff.objects.get(admin=request.user).role}
    except Staff.DoesNotExist:
        return {"staff_role": "instructor"}


def operational_alerts(request):
    if not request.user.is_authenticated:
        return {"pending_fee_alert_count": 0, "new_enrollments_today_count": 0}
    ut = str(getattr(request.user, "user_type", "") or "").strip()
    if ut not in ("1", "2"):
        return {"pending_fee_alert_count": 0, "new_enrollments_today_count": 0}
    if ut == "2":
        try:
            role = Staff.objects.get(admin=request.user).role
        except Staff.DoesNotExist:
            role = "instructor"
        if role not in ("admission", "finance"):
            return {"pending_fee_alert_count": 0, "new_enrollments_today_count": 0}
    pending = 0
    for st in Student.objects.select_related("course"):
        try:
            if st.balance() > 0:
                pending += 1
        except Exception:
            pass
    today = timezone.localdate()
    new_today = Student.objects.filter(enrollment_date=today).count()
    return {
        "pending_fee_alert_count": pending,
        "new_enrollments_today_count": new_today,
    }


def active_session_context(request):
    session = Session.objects.active().first()
    if session is None:
        session = Session.objects.latest_first().first()
    return {
        "current_active_session": session,
    }
