"""Set payment.course_id from enrollment when missing (SQLite)."""
from django.db import migrations


def backfill_course(apps, schema_editor):
    if schema_editor.connection.vendor != "sqlite":
        return
    with schema_editor.connection.cursor() as cursor:
        # Some deployments may have schema drift where this migration runs
        # before the enrollment table exists. Skip safely in that case.
        cursor.execute(
            """
            SELECT name FROM sqlite_master
            WHERE type='table' AND name IN ('main_app_payment', 'main_app_enrollment')
            """
        )
        present = {row[0] for row in cursor.fetchall()}
        if "main_app_payment" not in present or "main_app_enrollment" not in present:
            return
        cursor.execute(
            """
            UPDATE main_app_payment
            SET course_id = (
                SELECT e.course_id FROM main_app_enrollment e
                WHERE e.id = main_app_payment.enrollment_id
            )
            WHERE enrollment_id IS NOT NULL
              AND (course_id IS NULL OR course_id = 0)
            """
        )


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("main_app", "0016_fix_payment_table_missing_course_fk"),
    ]

    operations = [
        migrations.RunPython(backfill_course, noop_reverse),
    ]
