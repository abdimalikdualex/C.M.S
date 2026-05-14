"""Kenya-local date/datetime display for templates (shared with PDF/CSV helpers)."""

from __future__ import annotations

from django import template
from django.utils.dateparse import parse_date

from ..datetime_display import format_date, format_dt

register = template.Library()


@register.filter
def eat_date(value):
    """
    Date as DD/MM/YYYY in Nairobi context. Accepts date objects or YYYY-MM-DD strings
    (e.g. leave requests stored in a CharField).
    """
    if value in (None, ""):
        return ""
    if hasattr(value, "year") and hasattr(value, "month") and hasattr(value, "day"):
        return format_date(value)
    s = str(value).strip()
    d = parse_date(s[:10]) if len(s) >= 10 else None
    if d:
        return format_date(d)
    return s


@register.filter
def eat_datetime(value):
    """Aware or naive datetime → DD/MM/YYYY hh:mm AM/PM (Africa/Nairobi)."""
    if value in (None, ""):
        return ""
    return format_dt(value)
