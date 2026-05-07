"""
One-off and repeatable cleanup for legacy money data (whole KES, fee invariants).

Used by migration 0026 and the `retroactive_fee_cleanup` management command.
Pass historical ORM model classes from migrations, or live models from the command.
"""

from __future__ import annotations

from django.db.models import Sum

from .money import quantize_kes


def int_money(value) -> int:
    """Coerce stored money to whole KES (truncates legacy fractional values)."""
    return quantize_kes(value)


def _legacy_total_fee(course) -> int:
    if course is None:
        return 0
    payment_plan = getattr(course, "payment_plan", None) or "full"
    full_fee = int_money(getattr(course, "full_fee", 0))
    monthly_fee = int_money(getattr(course, "monthly_fee", 0))
    if payment_plan == "monthly":
        dv = int(getattr(course, "duration_value", 0) or 0)
        du = getattr(course, "duration_unit", None) or "weeks"
        if dv <= 0:
            return monthly_fee
        if du == "months":
            months = dv
        else:
            months = max(1, (dv + 3) // 4)
        return int_money(months * monthly_fee)
    return full_fee


def normalize_all_payments(Payment) -> int:
    n = 0
    for p in Payment.objects.all().only("id", "amount").iterator():
        old = getattr(p, "amount", 0)
        a = int_money(old)
        if a != old:
            Payment.objects.filter(pk=p.pk).update(amount=a)
            n += 1
    return n


def normalize_all_courses(Course) -> int:
    n = 0
    for c in Course.objects.all().only("id", "full_fee", "monthly_fee").iterator():
        old_ff = getattr(c, "full_fee", 0)
        old_mf = getattr(c, "monthly_fee", 0)
        ff = int_money(old_ff)
        mf = int_money(old_mf)
        if ff != old_ff or mf != old_mf:
            Course.objects.filter(pk=c.pk).update(full_fee=ff, monthly_fee=mf)
            n += 1
    return n


def cleanup_enrollment_fees(Enrollment, Payment) -> int:
    """
    For every enrollment:
    - If not cancelled: replace legacy auto totals with max(full_fee, paid), or fix zero fees.
    - Always: total_fee >= sum(payments), all whole KES.

    Preserves manual agreed fees that do not match the old legacy formula.
    """
    updated = 0
    for e in Enrollment.objects.select_related("course").iterator():
        paid = int(
            Payment.objects.filter(enrollment_id=e.pk).aggregate(t=Sum("amount"))["t"] or 0
        )
        paid = int_money(paid)
        orig = int_money(getattr(e, "total_fee", 0))
        course = getattr(e, "course", None)
        full = int_money(getattr(course, "full_fee", 0)) if course else 0
        leg = _legacy_total_fee(course)
        target_full = max(full, paid)

        new_tf = orig
        status = getattr(e, "status", "") or ""
        if status != "cancelled":
            if (orig == leg and target_full != orig) or (
                orig == 0 and full > 0 and target_full != orig
            ):
                new_tf = target_full
        new_tf = max(new_tf, paid)
        new_tf = int_money(new_tf)

        if new_tf != orig:
            Enrollment.objects.filter(pk=e.pk).update(total_fee=new_tf)
            updated += 1
    return updated


def run_full_retroactive_cleanup(*, Payment, Course, Enrollment, log=None) -> dict:
    """Run payment + course normalization, then enrollment cleanup. Returns counts."""
    def _say(msg):
        if log:
            log(msg)

    n_pay = normalize_all_payments(Payment)
    _say(f"Normalized {n_pay} payment row(s).")
    n_crs = normalize_all_courses(Course)
    _say(f"Normalized {n_crs} course row(s).")
    n_enr = cleanup_enrollment_fees(Enrollment, Payment)
    _say(f"Updated {n_enr} enrollment row(s).")
    return {"payments": n_pay, "courses": n_crs, "enrollments": n_enr}
