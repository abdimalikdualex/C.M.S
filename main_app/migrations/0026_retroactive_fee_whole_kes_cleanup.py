# Data cleanup: whole KES everywhere, fee invariants, legacy auto-fee correction.

from django.db import migrations


def forwards(apps, schema_editor):
    from main_app.fee_retroactive import run_full_retroactive_cleanup

    Payment = apps.get_model("main_app", "Payment")
    Course = apps.get_model("main_app", "Course")
    Enrollment = apps.get_model("main_app", "Enrollment")
    run_full_retroactive_cleanup(Payment=Payment, Course=Course, Enrollment=Enrollment)


def backwards(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("main_app", "0025_fix_enrollment_fees_align_full_fee"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
