"""
Repair SQLite schema when main_app_payment is missing course_id while
Django models expect Payment.course (common DB drift).
"""
from django.db import migrations


def _existing_columns(schema_editor):
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("PRAGMA table_info(main_app_payment)")
        return {row[1] for row in cursor.fetchall()}


def repair_payment_course_fk(apps, schema_editor):
    if schema_editor.connection.vendor != "sqlite":
        return
    cols = _existing_columns(schema_editor)
    if "course_id" in cols:
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(
            "ALTER TABLE main_app_payment ADD COLUMN course_id bigint NULL "
            "REFERENCES main_app_course (id) DEFERRABLE INITIALLY DEFERRED"
        )


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("main_app", "0015_enrollment_and_payment_link"),
    ]

    operations = [
        migrations.RunPython(repair_payment_course_fk, noop_reverse),
    ]
