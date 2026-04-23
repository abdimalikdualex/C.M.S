"""Idempotent management command that ensures a default HOD account exists.

Runs automatically during deploys (see `build.sh` and the Procfile `release`
phase) so freshly provisioned production databases are never left without a
login account.

Credentials are read from the environment so the default can be overridden
per-environment without code changes:

    DEFAULT_ADMIN_EMAIL        (default: "admin@elevate.college")
    DEFAULT_ADMIN_PASSWORD     (default: "ElevateAdmin@2026")
    DEFAULT_ADMIN_FULL_NAME    (default: "System Administrator")

If a user with the given email already exists, the command only resets the
password when `--reset-password` is passed (or `RESET_DEFAULT_ADMIN_PASSWORD=1`
is set in the environment). Existing deployments therefore keep whatever
password the HOD has already chosen.
"""

from __future__ import annotations

import os

from django.core.management.base import BaseCommand
from django.db import transaction

from main_app.models import CustomUser


DEFAULT_EMAIL = "admin@elevate.college"
DEFAULT_PASSWORD = "ElevateAdmin@2026"
DEFAULT_FULL_NAME = "System Administrator"


class Command(BaseCommand):
    help = "Create (or refresh) the default HOD/superuser account used after a fresh deploy."

    def add_arguments(self, parser):
        parser.add_argument(
            "--email",
            default=os.environ.get("DEFAULT_ADMIN_EMAIL", DEFAULT_EMAIL),
            help="Email address for the default admin account.",
        )
        parser.add_argument(
            "--password",
            default=os.environ.get("DEFAULT_ADMIN_PASSWORD", DEFAULT_PASSWORD),
            help="Password for the default admin account.",
        )
        parser.add_argument(
            "--full-name",
            default=os.environ.get("DEFAULT_ADMIN_FULL_NAME", DEFAULT_FULL_NAME),
            help="Display name for the default admin account.",
        )
        parser.add_argument(
            "--reset-password",
            action="store_true",
            default=os.environ.get("RESET_DEFAULT_ADMIN_PASSWORD", "").strip().lower()
            in {"1", "true", "yes"},
            help="If set, overwrite the password of an existing account.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        email = (options["email"] or "").strip().lower()
        password = options["password"] or ""
        full_name = (options["full_name"] or "").strip()
        reset_password = bool(options["reset_password"])

        if not email or not password:
            self.stdout.write(self.style.WARNING(
                "Skipping default admin bootstrap: email or password is empty."
            ))
            return

        user = CustomUser.objects.filter(email__iexact=email).first()

        if user is None:
            user = CustomUser.objects.create_user(
                email=email,
                password=password,
                full_name=full_name,
                user_type="1",
                is_staff=True,
                is_superuser=True,
                is_active=True,
            )
            self.stdout.write(self.style.SUCCESS(
                f"Created default HOD account <{email}>."
            ))
            return

        changed_fields = []
        if not user.is_active:
            user.is_active = True
            changed_fields.append("is_active")
        if not user.is_staff:
            user.is_staff = True
            changed_fields.append("is_staff")
        if not user.is_superuser:
            user.is_superuser = True
            changed_fields.append("is_superuser")
        if str(user.user_type).strip() != "1":
            user.user_type = "1"
            changed_fields.append("user_type")
        if full_name and not (user.full_name or "").strip():
            user.full_name = full_name
            changed_fields.append("full_name")

        if reset_password:
            user.set_password(password)
            changed_fields.append("password")

        if changed_fields:
            user.save(update_fields=changed_fields)
            self.stdout.write(self.style.SUCCESS(
                f"Updated default HOD account <{email}>: {', '.join(changed_fields)}."
            ))
        else:
            self.stdout.write(
                f"Default HOD account <{email}> already present; nothing to do."
            )
