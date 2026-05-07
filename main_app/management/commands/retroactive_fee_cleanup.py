"""Re-run global fee normalization (same logic as migration 0026)."""

from __future__ import annotations

from django.core.management.base import BaseCommand

from main_app.fee_retroactive import run_full_retroactive_cleanup
from main_app.models import Course, Enrollment, Payment


class Command(BaseCommand):
    help = (
        "Normalize all payment/course money fields to whole KES and fix enrollment "
        "total_fee (legacy auto totals, zero fees, and total_fee < paid). "
        "Idempotent; safe to run after deploy or on a restored database."
    )

    def handle(self, *args, **options):
        def log(msg):
            self.stdout.write(msg)

        stats = run_full_retroactive_cleanup(
            Payment=Payment, Course=Course, Enrollment=Enrollment, log=log
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"Done: payments={stats['payments']}, courses={stats['courses']}, "
                f"enrollments={stats['enrollments']}"
            )
        )
