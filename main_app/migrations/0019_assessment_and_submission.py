# Generated manually for instructor → student assessments MVP

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("main_app", "0018_quantize_money_whole_kes"),
    ]

    operations = [
        migrations.CreateModel(
            name="Assessment",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=255)),
                ("description", models.TextField(blank=True, default="")),
                ("due_date", models.DateTimeField()),
                (
                    "file",
                    models.FileField(
                        blank=True,
                        null=True,
                        upload_to="assessments/instructions/",
                    ),
                ),
                (
                    "closes_at_deadline",
                    models.BooleanField(
                        default=False,
                        help_text="If set, students cannot submit or update after the due date.",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "course",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="assessments",
                        to="main_app.course",
                    ),
                ),
                (
                    "instructor",
                    models.ForeignKey(
                        help_text="Instructor who created this assessment.",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="assessments_created",
                        to="main_app.staff",
                    ),
                ),
                (
                    "session",
                    models.ForeignKey(
                        blank=True,
                        help_text="Optional intake/session scope.",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="assessments",
                        to="main_app.session",
                    ),
                ),
            ],
            options={
                "ordering": ("-due_date", "-created_at"),
            },
        ),
        migrations.CreateModel(
            name="Submission",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "file",
                    models.FileField(
                        blank=True,
                        null=True,
                        upload_to="assessments/submissions/",
                    ),
                ),
                ("text_answer", models.TextField(blank=True, default="")),
                ("submitted_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("grade", models.IntegerField(blank=True, null=True)),
                ("feedback", models.TextField(blank=True, default="")),
                (
                    "assessment",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="submissions",
                        to="main_app.assessment",
                    ),
                ),
                (
                    "student",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="assessment_submissions",
                        to="main_app.student",
                    ),
                ),
            ],
            options={
                "ordering": ("-submitted_at",),
            },
        ),
        migrations.AddConstraint(
            model_name="submission",
            constraint=models.UniqueConstraint(
                fields=("assessment", "student"),
                name="uniq_assessment_student_submission",
            ),
        ),
    ]
