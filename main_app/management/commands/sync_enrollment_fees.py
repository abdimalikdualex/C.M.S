from __future__ import annotations

from django.core.management.base import BaseCommand

from main_app.fee_sync import enrollment_paid_sum, should_sync_enrollment_fee
from main_app.models import Enrollment
from main_app.money import quantize_kes


class Command(BaseCommand):
    help = (
        "Align Enrollment.total_fee with Course.full_fee for existing rows (legacy auto-fee fix). "
        "By default only updates enrollments whose fee still matches the old formula or is zero."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--all-active",
            action="store_true",
            help="Update every non-cancelled enrollment to max(course.full_fee, paid). "
            "This overwrites manual discounts below full fee.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print changes without saving.",
        )
        parser.add_argument(
            "--include-cancelled",
            action="store_true",
            help="Also process cancelled enrollments.",
        )

    def handle(self, *args, **options):
        dry = options["dry_run"]
        all_active = options["all_active"]
        include_cancelled = options["include_cancelled"]

        qs = Enrollment.objects.select_related("course").order_by("id")
        if not include_cancelled:
            qs = qs.exclude(status="cancelled")

        updated = 0
        preview = []

        for e in qs.iterator():
            course = e.course
            if course is None:
                continue
            cur = quantize_kes(e.total_fee or 0)
            paid = enrollment_paid_sum(e)
            full = quantize_kes(course.full_fee or 0)
            target = max(full, paid)

            if all_active:
                if target != cur:
                    preview.append((e.pk, cur, target, "force"))
                    if not dry:
                        Enrollment.objects.filter(pk=e.pk).update(total_fee=target)
                    updated += 1
                continue

            do_update, new_fee = should_sync_enrollment_fee(e, course)
            if do_update and new_fee != cur:
                preview.append((e.pk, cur, new_fee, "safe"))
                if not dry:
                    Enrollment.objects.filter(pk=e.pk).update(total_fee=new_fee)
                updated += 1

        for pk, old, new, mode in preview[:500]:
            self.stdout.write(f"enrollment {pk}: {old} -> {new} ({mode})")
        if len(preview) > 500:
            self.stdout.write(self.style.WARNING(f"... {len(preview) - 500} more (output truncated)"))

        if dry:
            self.stdout.write(self.style.WARNING(f"Dry run: would update {updated} enrollment(s)."))
        else:
            self.stdout.write(self.style.SUCCESS(f"Updated {updated} enrollment(s)."))
