"""Template filters for whole-KES amounts (no decimal formatting)."""

from django import template

from ..money import quantize_kes

register = template.Library()


@register.filter
def kes_intcomma(value):
    """Thousands-separated whole KES (e.g. 8000 -> '8,000')."""
    return f"{quantize_kes(value):,}"
