"""
Repair SQLite schema when main_app_payment is missing student_id while
migrations are marked applied (DB drift scenario).
"""
from django.db import migrations


def _existing_columns(schema_editor):
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("PRAGMA table_info(main_app_payment)")
        return {row[1] for row in cursor.fetchall()}


def repair_payment_student_fk(apps, schema_editor):
    if schema_editor.connection.vendor != "sqlite":
        return
    cols = _existing_columns(schema_editor)
    if "student_id" in cols:
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(
            "ALTER TABLE main_app_payment ADD COLUMN student_id bigint NULL "
            "REFERENCES main_app_student (id) DEFERRABLE INITIALLY DEFERRED"
        )


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("main_app", "0013_fix_student_table_missing_fk_columns"),
    ]

    operations = [
        migrations.RunPython(repair_payment_student_fk, noop_reverse),
    ]

