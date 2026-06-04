"""Verify the default database connection (run on Render Shell or start.sh)."""

from django.core.management.base import BaseCommand
from django.db import connection


class Command(BaseCommand):
    help = "Test database connectivity; exits non-zero if the database is unreachable."

    def handle(self, *args, **options):
        db = connection.settings_dict
        host = db.get("HOST", "?")
        name = db.get("NAME", "?")
        self.stdout.write(f"Connecting to {host} / {name} …")
        connection.ensure_connection()
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        self.stdout.write(self.style.SUCCESS("Database connection OK."))
