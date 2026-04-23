from django.db import migrations, models


def _table_columns(connection, table_name):
    try:
        with connection.cursor() as cursor:
            desc = connection.introspection.get_table_description(cursor, table_name)
        return {col.name for col in desc}
    except Exception:
        return set()


def forwards(apps, schema_editor):
    """
    Schema-drift-safe integer conversion:
    avoid ORM iteration because legacy DBs may miss model columns (e.g. enrollment_id).
    """
    conn = schema_editor.connection
    tables = set(conn.introspection.table_names())

    with conn.cursor() as cursor:
        if "main_app_payment" in tables:
            cols = _table_columns(conn, "main_app_payment")
            if "student_id" in cols:
                # Remove broken rows only when student_id column exists.
                cursor.execute("DELETE FROM main_app_payment WHERE student_id IS NULL")
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
        ("main_app", "0019_assessment_and_submission"),
    ]

    operations = [
        migrations.RunPython(forwards, noop_reverse),
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
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
            ],
        ),
    ]
