# Generated for Phase 1: explicit Session.is_active flag.

from django.db import migrations, models


def backfill_active_session(apps, schema_editor):
    Session = apps.get_model("main_app", "Session")
    if Session.objects.filter(is_active=True).exists():
        return
    # Prefer the most recent session whose date range covers today; else the latest.
    from django.utils import timezone

    today = timezone.localdate()
    candidate = (
        Session.objects.filter(start_year__lte=today, end_year__gte=today)
        .order_by("-start_year", "-end_year", "-id")
        .first()
    )
    if candidate is None:
        candidate = Session.objects.order_by("-start_year", "-end_year", "-id").first()
    if candidate is not None:
        candidate.is_active = True
        candidate.save(update_fields=["is_active"])


def noop_reverse(apps, schema_editor):
    return


class Migration(migrations.Migration):

    dependencies = [
        ("main_app", "0021_alter_assessment_options_alter_submission_options_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="session",
            name="is_active",
            field=models.BooleanField(
                default=False,
                help_text="Mark exactly one session as the current intake. New registrations default to it.",
            ),
        ),
        migrations.RunPython(backfill_active_session, noop_reverse),
    ]
