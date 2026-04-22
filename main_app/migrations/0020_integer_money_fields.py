from decimal import Decimal

from django.db import migrations, models


def _to_int(value):
    if value is None:
        return 0
    return int(Decimal(str(value)))


def forwards(apps, schema_editor):
    Payment = apps.get_model("main_app", "Payment")
    # Legacy local DB safety: remove broken rows that cannot satisfy NOT NULL FK constraints.
    Payment.objects.filter(student_id__isnull=True).delete()
    for p in Payment.objects.all().iterator():
        new_amt = _to_int(p.amount)
        if new_amt != p.amount:
            p.amount = new_amt
            p.save(update_fields=["amount"])

    Course = apps.get_model("main_app", "Course")
    for c in Course.objects.all().iterator():
        nf = _to_int(c.full_fee)
        nm = _to_int(c.monthly_fee)
        if nf != c.full_fee or nm != c.monthly_fee:
            c.full_fee = nf
            c.monthly_fee = nm
            c.save(update_fields=["full_fee", "monthly_fee"])

    Enrollment = apps.get_model("main_app", "Enrollment")
    for e in Enrollment.objects.all().iterator():
        nt = _to_int(e.total_fee)
        if nt != e.total_fee:
            e.total_fee = nt
            e.save(update_fields=["total_fee"])


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("main_app", "0019_assessment_and_submission"),
    ]

    operations = [
        migrations.RunPython(forwards, noop_reverse),
        migrations.AlterField(
            model_name="course",
            name="full_fee",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AlterField(
            model_name="course",
            name="monthly_fee",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AlterField(
            model_name="enrollment",
            name="total_fee",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AlterField(
            model_name="payment",
            name="amount",
            field=models.PositiveIntegerField(),
        ),
    ]
