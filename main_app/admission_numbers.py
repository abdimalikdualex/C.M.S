"""
Official admission numbers: EDH/YYYY/NNN (ELEVATE DIGITAL HUB).
Sequential per calendar year; resets each year via AdmissionSequence.
"""
from __future__ import annotations

import re
from django.db import transaction

EDH_PREFIX = "EDH"
# EDH/2026/1 … EDH/2026/999 … EDH/2026/1000 (minimum 3 digits when < 1000 via formatter)
ADMISSION_PATTERN = re.compile(r"^EDH/(?P<year>\d{4})/(?P<seq>\d+)$")


def normalize_admission_input(value: str | None) -> str:
    """Normalize user-typed admission numbers (e.g. edh/2026/001 → EDH/2026/001)."""
    s = (value or "").strip()
    if len(s) >= 4 and s[:4].lower() == "edh/":
        return "EDH/" + s[4:].strip()
    return s


def is_valid_admission_number(value: str | None) -> bool:
    if not value or not str(value).strip():
        return False
    return bool(ADMISSION_PATTERN.fullmatch(str(value).strip()))


def format_admission_number(year: int, seq: int) -> str:
    """Human-readable admission number (seq zero-padded to at least 3 digits)."""
    return f"EDH/{year}/{seq:03d}"


def allocate_next_admission_number(year: int) -> str:
    """
    Next number for the given year (thread-safe under concurrent enrollments).
    """
    # Local import avoids circular import
    from .models import AdmissionSequence

    with transaction.atomic():
        row, _ = AdmissionSequence.objects.select_for_update().get_or_create(
            year=int(year),
            defaults={"last_value": 0},
        )
        row.last_value = int(row.last_value) + 1
        row.save(update_fields=["last_value"])
        return format_admission_number(int(year), row.last_value)


def sync_counter_from_existing_students() -> None:
    """Repair AdmissionSequence.last_value from current Student rows (admin/maintenance)."""
    from collections import defaultdict

    from .models import AdmissionSequence, Student

    max_seq: dict[int, int] = defaultdict(int)
    for sid in Student.objects.values_list("student_id", flat=True):
        if not sid:
            continue
        m = ADMISSION_PATTERN.fullmatch(str(sid).strip())
        if not m:
            continue
        y = int(m.group("year"))
        n = int(m.group("seq"))
        max_seq[y] = max(max_seq[y], n)
    for year, n in max_seq.items():
        AdmissionSequence.objects.update_or_create(
            year=year,
            defaults={"last_value": n},
        )
