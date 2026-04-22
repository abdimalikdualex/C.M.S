"""
Repair SQLite schema when main_app_student is missing course_id / session_id /
enrollment_date while migrations are marked applied (common after DB swaps or manual edits).
"""
from django.db import migrations
from django.utils import timezone


def _existing_columns(schema_editor):
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("PRAGMA table_info(main_app_student)")
        return {row[1] for row in cursor.fetchall()}


def repair_student_columns(apps, schema_editor):
    if schema_editor.connection.vendor != "sqlite":
        return
    cols = _existing_columns(schema_editor)
    today = timezone.now().date().isoformat()
    with schema_editor.connection.cursor() as cursor:
        if "course_id" not in cols:
            cursor.execute(
                "ALTER TABLE main_app_student ADD COLUMN course_id bigint NULL "
                "REFERENCES main_app_course (id) DEFERRABLE INITIALLY DEFERRED"
            )
        if "session_id" not in cols:
            cursor.execute(
                "ALTER TABLE main_app_student ADD COLUMN session_id bigint NULL "
                "REFERENCES main_app_session (id) DEFERRABLE INITIALLY DEFERRED"
            )
        if "enrollment_date" not in cols:
            cursor.execute(
                f"ALTER TABLE main_app_student ADD COLUMN enrollment_date date NOT NULL DEFAULT '{today}'"
            )


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("main_app", "0012_customuser_full_name"),
    ]

    operations = [
        migrations.RunPython(repair_student_columns, noop_reverse),
    ]
