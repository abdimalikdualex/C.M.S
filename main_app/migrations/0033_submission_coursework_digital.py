# Generated manually for universal digital coursework submissions.

from django.db import migrations, models
import django.db.models.deletion


def sync_review_status_from_grade(apps, schema_editor):
    Submission = apps.get_model("main_app", "Submission")
    for row in Submission.objects.iterator():
        has_feedback = bool((getattr(row, "feedback", None) or "").strip())
        if row.grade is not None or has_feedback:
            row.review_status = "reviewed"
            row.save(update_fields=["review_status"])


class Migration(migrations.Migration):
    dependencies = [
        ("main_app", "0032_kenya_local_date_defaults"),
    ]

    operations = [
        migrations.AddField(
            model_name="submission",
            name="github_url",
            field=models.URLField(blank=True, default="", max_length=500),
        ),
        migrations.AddField(
            model_name="submission",
            name="portfolio_url",
            field=models.URLField(blank=True, default="", max_length=500),
        ),
        migrations.AddField(
            model_name="submission",
            name="video_url",
            field=models.URLField(blank=True, default="", max_length=500),
        ),
        migrations.AddField(
            model_name="submission",
            name="review_status",
            field=models.CharField(
                choices=[
                    ("submitted", "Submitted — awaiting review"),
                    ("reviewed", "Reviewed"),
                    ("approved", "Approved"),
                ],
                db_index=True,
                default="submitted",
                max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name="submission",
            name="file",
            field=models.FileField(
                blank=True,
                help_text="Primary file (legacy / first upload). Additional files use attachments.",
                null=True,
                upload_to="assessments/submissions/",
            ),
        ),
        migrations.CreateModel(
            name="SubmissionAttachment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("file", models.FileField(upload_to="assessments/submissions/extra/")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "submission",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="attachments",
                        to="main_app.submission",
                    ),
                ),
            ],
            options={
                "ordering": ["id"],
            },
        ),
        migrations.RunPython(sync_review_status_from_grade, migrations.RunPython.noop),
    ]
