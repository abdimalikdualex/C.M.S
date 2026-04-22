from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ("main_app", "0014_fix_payment_table_missing_student_fk"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.CreateModel(
                    name="Enrollment",
                    fields=[
                        ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                        ("start_date", models.DateField(default=django.utils.timezone.now)),
                        ("total_fee", models.DecimalField(decimal_places=2, default=0, max_digits=10)),
                        ("status", models.CharField(choices=[("active", "Active"), ("completed", "Completed"), ("cancelled", "Cancelled")], default="active", max_length=20)),
                        ("enrollment_level", models.CharField(blank=True, choices=[("", "N/A"), ("beginner", "Beginner"), ("intermediate", "Intermediate"), ("advanced", "Advanced")], default="", max_length=20)),
                        ("created_at", models.DateTimeField(auto_now_add=True)),
                        ("updated_at", models.DateTimeField(auto_now=True)),
                        ("assigned_instructor", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="assigned_enrollments", to="main_app.staff")),
                        ("course", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="enrollments", to="main_app.course")),
                        ("session", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to="main_app.session")),
                        ("student", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="enrollments", to="main_app.student")),
                    ],
                    options={"ordering": ["-created_at"]},
                ),
                migrations.AddConstraint(
                    model_name="enrollment",
                    constraint=models.UniqueConstraint(fields=("student", "course"), name="uniq_student_course_enrollment"),
                ),
                migrations.AddField(
                    model_name="payment",
                    name="enrollment",
                    field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="payments", to="main_app.enrollment"),
                ),
            ],
        ),
    ]

