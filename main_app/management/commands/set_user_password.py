"""Set or reset a user's password by email (Render Shell recovery)."""

from __future__ import annotations

import os

from django.core.management.base import BaseCommand

from main_app.models import Admin, CustomUser


class Command(BaseCommand):
    help = "Set password for an existing user, or create a HOD account if missing."

    def add_arguments(self, parser):
        parser.add_argument(
            "--email",
            default=os.environ.get("DEFAULT_ADMIN_EMAIL", "").strip(),
            required=False,
        )
        parser.add_argument(
            "--password",
            default=os.environ.get("DEFAULT_ADMIN_PASSWORD", "").strip(),
            required=False,
        )
        parser.add_argument(
            "--full-name",
            default=os.environ.get("DEFAULT_ADMIN_FULL_NAME", "System Administrator"),
        )
        parser.add_argument(
            "--hod",
            action="store_true",
            default=True,
            help="Ensure user is HOD (user_type=1) with Admin profile.",
        )

    def handle(self, *args, **options):
        email = (options["email"] or "").strip().lower()
        password = options["password"] or ""
        if not email or not password:
            self.stderr.write("Provide --email and --password (or DEFAULT_ADMIN_EMAIL / DEFAULT_ADMIN_PASSWORD).")
            return

        user = CustomUser.objects.filter(email__iexact=email).first()
        if user is None:
            user = CustomUser.objects.create_user(
                email=email,
                password=password,
                full_name=(options["full_name"] or "").strip(),
                user_type="1",
                is_staff=True,
                is_superuser=True,
                is_active=True,
            )
            self.stdout.write(self.style.SUCCESS(f"Created account <{email}>."))
        else:
            user.set_password(password)
            user.is_active = True
            user.is_staff = True
            user.is_superuser = True
            if options["hod"]:
                user.user_type = "1"
            user.save()
            self.stdout.write(self.style.SUCCESS(f"Updated password for <{email}>."))

        if options["hod"]:
            if str(user.user_type).strip() != "1":
                user.user_type = "1"
                user.save(update_fields=["user_type"])
            if not Admin.objects.filter(admin=user).exists():
                Admin.objects.create(admin=user)
