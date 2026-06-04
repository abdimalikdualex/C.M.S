"""
Copy records from local db.sqlite3 into the active database without deleting anything.

- Only INSERTS missing rows (matched by primary key or natural keys like email / student_id).
- Never deletes, truncates, or updates existing production rows (except skipped duplicates).
- Preserves password hashes from the SQLite backup as-is.

Usage (from project root, with DATABASE_URL pointing at production Postgres):

    python manage.py merge_sqlite_data --dry-run
    python manage.py merge_sqlite_data

Optional: --sqlite path/to/db.sqlite3  (default: BASE_DIR/db.sqlite3)
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction

from main_app.models import (
    Admin,
    Course,
    CustomUser,
    Session,
    Staff,
    Student,
)


class Command(BaseCommand):
    help = "Additively merge data from local db.sqlite3 into the current database (no deletes)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--sqlite",
            default=str(Path(settings.BASE_DIR) / "db.sqlite3"),
            help="Path to the SQLite file to read from.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be copied without writing.",
        )

    def handle(self, *args, **options):
        sqlite_path = Path(options["sqlite"])
        dry_run = bool(options["dry_run"])

        if not sqlite_path.is_file():
            self.stderr.write(self.style.ERROR(f"SQLite file not found: {sqlite_path}"))
            return

        conn = sqlite3.connect(sqlite_path)
        conn.row_factory = sqlite3.Row

        stats = {"users": 0, "sessions": 0, "courses": 0, "staff": 0, "students": 0, "skipped": 0}

        def log(msg):
            self.stdout.write(msg)

        with transaction.atomic():
            stats["sessions"] = self._merge_sessions(conn, dry_run, log)
            stats["courses"] = self._merge_courses(conn, dry_run, log)
            stats["users"] = self._merge_users(conn, dry_run, log, stats)
            stats["staff"] = self._merge_staff(conn, dry_run, log)
            stats["students"] = self._merge_students(conn, dry_run, log)

            if dry_run:
                transaction.set_rollback(True)
                log(self.style.WARNING("Dry run — no changes written."))

        self.stdout.write(self.style.SUCCESS(f"Merge complete: {stats}"))

    def _merge_sessions(self, conn, dry_run, log) -> int:
        added = 0
        for row in conn.execute("SELECT * FROM main_app_session"):
            if Session.objects.filter(pk=row["id"]).exists():
                continue
            if dry_run:
                log(f"  [dry-run] would add Session id={row['id']}")
            else:
                Session.objects.create(
                    id=row["id"],
                    start_year=row["start_year"],
                    end_year=row["end_year"],
                    is_active=bool(row.get("is_active", 0)),
                )
            added += 1
        return added

    def _merge_courses(self, conn, dry_run, log) -> int:
        added = 0
        for row in conn.execute("SELECT * FROM main_app_course"):
            if Course.objects.filter(pk=row["id"]).exists():
                continue
            if dry_run:
                log(f"  [dry-run] would add Course id={row['id']} {row.get('name', '')}")
            else:
                Course.objects.create(
                    id=row["id"],
                    name=row.get("name") or "",
                    duration_value=row.get("duration_value") or 0,
                    duration_unit=row.get("duration_unit") or "weeks",
                    payment_plan=row.get("payment_plan") or "full",
                    monthly_fee=row.get("monthly_fee") or 0,
                    full_fee=row.get("full_fee") or 0,
                    level=row.get("level") or "",
                    skills_track=row.get("skills_track") or "",
                    rolling_intake=bool(row.get("rolling_intake", 1)),
                    intake_start=row.get("intake_start"),
                    intake_end=row.get("intake_end"),
                )
            added += 1
        return added

    def _merge_users(self, conn, dry_run, log, stats) -> int:
        added = 0
        for row in conn.execute("SELECT * FROM main_app_customuser"):
            email = (row["email"] or "").strip().lower()
            if not email:
                stats["skipped"] += 1
                continue
            if CustomUser.objects.filter(email__iexact=email).exists():
                stats["skipped"] += 1
                continue
            if dry_run:
                log(f"  [dry-run] would add user {email}")
            else:
                user = CustomUser(
                    id=row["id"],
                    email=row["email"],
                    password=row["password"],
                    user_type=str(row.get("user_type") or "1"),
                    is_staff=bool(row.get("is_staff")),
                    is_superuser=bool(row.get("is_superuser")),
                    is_active=bool(row.get("is_active", 1)),
                    full_name=row.get("full_name") or "",
                    first_name=row.get("first_name") or "",
                    last_name=row.get("last_name") or "",
                    phone_number=row.get("phone_number") or "",
                    gender=row.get("gender") or "",
                    address=row.get("address") or "",
                    fcm_token=row.get("fcm_token") or "",
                )
                if row.get("profile_pic"):
                    user.profile_pic = row["profile_pic"]
                user.save()
                ut = str(user.user_type).strip()
                if ut == "1" and not Admin.objects.filter(admin=user).exists():
                    Admin.objects.create(admin=user)
            added += 1
        return added

    def _merge_staff(self, conn, dry_run, log) -> int:
        added = 0
        for row in conn.execute("SELECT * FROM main_app_staff"):
            if Staff.objects.filter(pk=row["id"]).exists():
                continue
            admin_id = row["admin_id"]
            if not CustomUser.objects.filter(pk=admin_id).exists():
                continue
            if dry_run:
                log(f"  [dry-run] would add Staff id={row['id']}")
            else:
                Staff.objects.create(
                    id=row["id"],
                    admin_id=admin_id,
                    course_id=row.get("course_id"),
                    role=row.get("role") or "instructor",
                )
            added += 1
        return added

    def _merge_students(self, conn, dry_run, log) -> int:
        added = 0
        for row in conn.execute("SELECT * FROM main_app_student"):
            sid = (row.get("student_id") or "").strip()
            if sid and Student.objects.filter(student_id__iexact=sid).exists():
                continue
            if Student.objects.filter(pk=row["id"]).exists():
                continue
            admin_id = row["admin_id"]
            if not CustomUser.objects.filter(pk=admin_id).exists():
                continue
            session_id = row.get("session_id")
            if session_id and not Session.objects.filter(pk=session_id).exists():
                session_id = Session.objects.active_or_latest().first()
                session_id = session_id.pk if session_id else None
            if dry_run:
                log(f"  [dry-run] would add Student {sid or row['id']}")
            else:
                Student.objects.create(
                    id=row["id"],
                    admin_id=admin_id,
                    course_id=row.get("course_id"),
                    session_id=session_id,
                    student_id=sid or None,
                    enrollment_date=row.get("enrollment_date"),
                )
            added += 1
        return added
