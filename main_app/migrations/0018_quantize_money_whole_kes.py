from django.db import migrations


def _table_columns(connection, table_name):
    try:
        with connection.cursor() as cursor:
            desc = connection.introspection.get_table_description(cursor, table_name)
        return {col.name for col in desc}
    except Exception:
        return set()


def forwards(apps, schema_editor):
    """
    Schema-drift-safe data cleanup:
    - Some deployments have partially-applied legacy migrations.
    - Avoid ORM model iteration here because selecting missing columns crashes.
    - Quantize by truncation to integer with SQL CAST only for columns that exist.
    """
    conn = schema_editor.connection
    tables = set(conn.introspection.table_names())

    with conn.cursor() as cursor:
        if "main_app_payment" in tables:
            cols = _table_columns(conn, "main_app_payment")
            if "amount" in cols:
                cursor.execute(
                    "UPDATE main_app_payment SET amount = CAST(amount AS INTEGER) WHERE amount IS NOT NULL"
                )

        if "main_app_course" in tables:
            cols = _table_columns(conn, "main_app_course")
            if "full_fee" in cols:
                cursor.execute(
                    "UPDATE main_app_course SET full_fee = CAST(full_fee AS INTEGER) WHERE full_fee IS NOT NULL"
                )
            if "monthly_fee" in cols:
                cursor.execute(
                    "UPDATE main_app_course SET monthly_fee = CAST(monthly_fee AS INTEGER) WHERE monthly_fee IS NOT NULL"
                )

        if "main_app_enrollment" in tables:
            cols = _table_columns(conn, "main_app_enrollment")
            if "total_fee" in cols:
                cursor.execute(
                    "UPDATE main_app_enrollment SET total_fee = CAST(total_fee AS INTEGER) WHERE total_fee IS NOT NULL"
                )


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("main_app", "0017_backfill_payment_course_from_enrollment"),
    ]

    operations = [
        migrations.RunPython(forwards, noop_reverse),
    ]
