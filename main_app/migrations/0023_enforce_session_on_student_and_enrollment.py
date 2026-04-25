# Generated for Phase 1: enforce session FK on Student and Enrollment.

from django.db import migrations, models
import django.db.models.deletion


def backfill_sessions(apps, schema_editor):
    Session = apps.get_model("main_app", "Session")
    Student = apps.get_model("main_app", "Student")
    Enrollment = apps.get_model("main_app", "Enrollment")

    fallback = (
        Session.objects.filter(is_active=True).order_by("-start_year", "-end_year", "-id").first()
    )
    if fallback is None:
        from django.utils import timezone

        today = timezone.localdate()
        fallback = (
            Session.objects.filter(start_year__lte=today, end_year__gte=today)
            .order_by("-start_year", "-end_year", "-id")
            .first()
        )
    if fallback is None:
        fallback = Session.objects.order_by("-start_year", "-end_year", "-id").first()

    if fallback is None:
        # No sessions exist; nothing we can do safely. Caller must create one
        # before re-running this migration; no rows will be affected.
        if Student.objects.filter(session__isnull=True).exists() or Enrollment.objects.filter(
            session__isnull=True
        ).exists():
            raise RuntimeError(
                "Cannot backfill Student/Enrollment.session: no Session rows exist. "
                "Create at least one Session in Django admin (or fixtures) and re-run migrations."
            )
        return

    Student.objects.filter(session__isnull=True).update(session=fallback)
    Enrollment.objects.filter(session__isnull=True).update(session=fallback)


def noop_reverse(apps, schema_editor):
    return


class Migration(migrations.Migration):

    dependencies = [
        ("main_app", "0022_session_is_active"),
    ]

    operations = [
        migrations.RunPython(backfill_sessions, noop_reverse),
        migrations.AlterField(
            model_name="student",
            name="session",
            field=models.ForeignKey(
                help_text="Intake/session the student belongs to. Required.",
                on_delete=django.db.models.deletion.PROTECT,
                to="main_app.session",
            ),
        ),
        migrations.AlterField(
            model_name="enrollment",
            name="session",
            field=models.ForeignKey(
                help_text="Intake/session the enrollment belongs to. Required.",
                on_delete=django.db.models.deletion.PROTECT,
                to="main_app.session",
            ),
        ),
    ]
