"""
Centralized audit trail — lightweight activity logging for accountability.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from django.http import HttpRequest

from .roles import get_dashboard_role, get_staff_role_key

logger = logging.getLogger(__name__)

ACTION_CREATE = "create"
ACTION_UPDATE = "update"
ACTION_DELETE = "delete"
ACTION_LOGIN = "login"
ACTION_LOGOUT = "logout"
ACTION_EXPORT = "export"
ACTION_OTHER = "other"

MODULE_AUTH = "Authentication"
MODULE_STUDENTS = "Students"
MODULE_COURSES = "Courses"
MODULE_SUBJECTS = "Subjects"
MODULE_SESSIONS = "Sessions"
MODULE_ENROLLMENT = "Enrollment"
MODULE_FEES = "Fees & Payments"
MODULE_ATTENDANCE = "Attendance"
MODULE_ASSIGNMENTS = "Assignments"
MODULE_INSTRUCTORS = "Instructors"
MODULE_REPORTS = "Reports"
MODULE_EVENTS = "Events"
MODULE_ASSESSMENTS = "Assessments"

KNOWN_MODULES = (
    MODULE_AUTH,
    MODULE_STUDENTS,
    MODULE_COURSES,
    MODULE_SUBJECTS,
    MODULE_SESSIONS,
    MODULE_ENROLLMENT,
    MODULE_FEES,
    MODULE_ATTENDANCE,
    MODULE_ASSIGNMENTS,
    MODULE_INSTRUCTORS,
    MODULE_REPORTS,
    MODULE_EVENTS,
    MODULE_ASSESSMENTS,
)


def client_ip(request: HttpRequest | None) -> str:
    if request is None:
        return ""
    xff = request.META.get("HTTP_X_FORWARDED_FOR") or ""
    if xff:
        return xff.split(",")[0].strip()[:45]
    return (request.META.get("REMOTE_ADDR") or "").strip()[:45]


def resolve_display_name(user) -> str:
    if not user or not getattr(user, "is_authenticated", False):
        return ""
    fn = (getattr(user, "full_name", None) or "").strip()
    if fn:
        return fn[:250]
    gn = user.get_full_name()
    if gn:
        return gn[:250]
    return (user.email or "")[:250]


def resolve_role_label(user) -> str:
    if not user or not getattr(user, "is_authenticated", False):
        return ""
    role = get_dashboard_role(user)
    if role == "superadmin":
        return "Superadmin"
    if role == "student":
        return "Student"
    if role == "instructor":
        sk = get_staff_role_key(user)
        if sk == "instructor":
            return "Instructor"
        if sk in ("admission", "finance"):
            return "Staff (desk)"
        return "Staff"
    return "User"


def log_audit(
    request: HttpRequest | None,
    *,
    module: str,
    activity: str,
    audit_action: str,
    target_record: str = "",
    detail: str = "",
    student=None,
    user=None,
) -> None:
    """Append-only audit row. Failures never block the main request."""
    try:
        from .models import AuditLog

        actor = user
        if actor is None and request is not None:
            actor = getattr(request, "user", None)
        if actor is not None and not getattr(actor, "is_authenticated", False):
            actor = None

        AuditLog.objects.create(
            user=actor,
            user_name=resolve_display_name(actor) if actor else "",
            user_role=resolve_role_label(actor) if actor else "",
            module=str(module or "")[:64],
            activity=str(activity or "")[:255],
            audit_action=str(audit_action or ACTION_OTHER)[:16],
            target_record=str(target_record or "")[:512],
            detail=(detail or "")[:8000],
            ip_address=client_ip(request),
            student=student if student is not None else None,
        )
    except Exception:
        logger.exception("Audit log failed for module=%s activity=%s", module, activity)
