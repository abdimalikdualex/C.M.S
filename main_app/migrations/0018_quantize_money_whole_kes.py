"""Round existing monetary columns to whole Kenyan shillings."""
from decimal import ROUND_HALF_UP, Decimal

from django.db import migrations


def _q1(value):
    if value is None:
        return Decimal("0")
    d = value if isinstance(value, Decimal) else Decimal(str(value))
    return d.quantize(Decimal("1"), rounding=ROUND_HALF_UP)


def forwards(apps, schema_editor):
    Payment = apps.get_model("main_app", "Payment")
    for p in Payment.objects.all().iterator():
        new_amt = _q1(p.amount)
        if new_amt != p.amount:
            p.amount = new_amt
            p.save(update_fields=["amount"])

    Course = apps.get_model("main_app", "Course")
    for c in Course.objects.all().iterator():
        nf = _q1(c.full_fee)
        nm = _q1(c.monthly_fee)
        if nf != c.full_fee or nm != c.monthly_fee:
            c.full_fee = nf
            c.monthly_fee = nm
            c.save(update_fields=["full_fee", "monthly_fee"])

    Enrollment = apps.get_model("main_app", "Enrollment")
    for e in Enrollment.objects.all().iterator():
        nt = _q1(e.total_fee)
        if nt != e.total_fee:
            e.total_fee = nt
            e.save(update_fields=["total_fee"])


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("main_app", "0017_backfill_payment_course_from_enrollment"),
    ]

    operations = [
        migrations.RunPython(forwards, noop_reverse),
    ]
