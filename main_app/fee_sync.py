"""
Align enrollment agreed fees with course full_fee after manual-fee-only rules.

Used by management command sync_enrollment_fees. Migration 0025 inlines the
same legacy formula so historical state stays reproducible.
"""

from __future__ import annotations

from django.db.models import Sum

from .money import quantize_kes


def legacy_total_fee_for_course(course) -> int:
    """Previous Course.total_fee_for_student() (monthly x duration or full_fee)."""
    payment_plan = getattr(course, "payment_plan", None) or "full"
    if payment_plan == "monthly":
        monthly = quantize_kes(getattr(course, "monthly_fee", 0))
        duration_value = int(getattr(course, "duration_value", 0) or 0)
        if duration_value <= 0:
            return quantize_kes(monthly)
        unit = getattr(course, "duration_unit", None) or "weeks"
        if unit == "months":
            months = duration_value
        else:
            months = max(1, (duration_value + 3) // 4)
        return quantize_kes(months * monthly)
    return quantize_kes(getattr(course, "full_fee", 0))


def enrollment_paid_sum(enrollment) -> int:
    return quantize_kes(
        enrollment.payments.aggregate(total=Sum("amount"))["total"] or 0
    )


def should_sync_enrollment_fee(enrollment, course) -> tuple[bool, int]:
    """
    Decide if enrollment.total_fee should be replaced and the target value.

    Returns (should_update, new_total_fee). new_total_fee is always max(full_fee, paid).

    Updates when:
    - Stored fee still matches the *legacy* auto total but course full_fee differs, or
    - Stored fee is zero while the course sets a positive full_fee (fix empty data).

    Skips when the stored fee differs from legacy (likely manual scholarship/override).
    """
    full = quantize_kes(getattr(course, "full_fee", 0))
    paid = enrollment_paid_sum(enrollment)
    target = max(full, paid)
    cur = quantize_kes(getattr(enrollment, "total_fee", 0))
    legacy = legacy_total_fee_for_course(course)

    if cur == legacy and target != cur:
        return True, target
    if cur == 0 and full > 0 and target != cur:
        return True, target
    return False, cur
