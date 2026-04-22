"""Whole-number KES helpers (integer-only)."""


def quantize_kes(value) -> int:
    """Normalize monetary value to whole KES integer."""
    if value is None:
        return 0
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    txt = str(value).strip()
    if not txt:
        return 0
    try:
        return int(txt)
    except (TypeError, ValueError):
        try:
            return int(float(txt))
        except (TypeError, ValueError):
            return 0


def max_zero_kes(value) -> int:
    """Non-negative whole KES."""
    z = quantize_kes(value)
    return z if z > 0 else 0


def format_money(value) -> int:
    """Whole-shilling KES as int (SMS, labels, APIs)."""
    return quantize_kes(value)
