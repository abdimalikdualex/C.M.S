"""
Kenya (Africa/Nairobi, EAT UTC+3) display formatting for PDFs, CSV exports, and receipts.
Matches templates: d/m/Y and d/m/Y h:i A (12-hour, en-gb formats).
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional, Union

from django.utils import dateformat
from django.utils import timezone as dj_tz

_FMT_DATE = "%d/%m/%Y"
_FMT_DATE_LONG = "%d %B %Y"


def _as_local_datetime(dt: datetime) -> datetime:
    if dj_tz.is_naive(dt):
        return dj_tz.make_aware(dt, dj_tz.get_default_timezone())
    return dj_tz.localtime(dt)


def format_dt(dt: Optional[Union[datetime, date]], *, seconds: bool = False) -> str:
    """Datetime in Nairobi local time, e.g. 12/05/2026 08:30 AM."""
    if dt is None:
        return "—"
    if isinstance(dt, date) and not isinstance(dt, datetime):
        return dt.strftime(_FMT_DATE)
    loc = _as_local_datetime(dt)
    if seconds:
        return dateformat.format(loc, "d/m/Y h:i:s A")
    return dateformat.format(loc, "d/m/Y h:i A")


def format_date(dt: Optional[Union[datetime, date]], *, long: bool = False) -> str:
    """Date only: 12/05/2026 or 12 May 2026 (long)."""
    if dt is None:
        return "—"
    if isinstance(dt, datetime):
        dt = _as_local_datetime(dt).date()
    if long:
        return dt.strftime(_FMT_DATE_LONG)
    return dt.strftime(_FMT_DATE)


def format_filename_ts(now: Optional[datetime] = None) -> str:
    """Compact local timestamp for export filenames."""
    t = now if now is not None else dj_tz.now()
    return dj_tz.localtime(t).strftime("%Y%m%d-%H%M")


def format_receipt_day_stamp(now: Optional[datetime] = None) -> str:
    """YYYYMMDD segment for receipt numbers (Nairobi calendar day)."""
    t = now if now is not None else dj_tz.now()
    return dj_tz.localtime(t).strftime("%Y%m%d")
