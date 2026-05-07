"""Whole-number KES helpers (integer-only)."""

WHOLE_KES_MSG = "Only whole-number fee amounts are allowed."


def quantize_kes(value) -> int:
    """Normalize monetary value to whole KES integer (internal/display only)."""
    if value is None:
        return 0
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    txt = str(value).strip().replace(",", "")
    if not txt:
        return 0
    try:
        return int(txt)
    except (TypeError, ValueError):
        try:
            return int(float(txt))
        except (TypeError, ValueError):
            return 0


def parse_post_whole_kes(raw) -> int:
    """
    Parse fee/payment amounts from POST or free text: whole non-negative integers only.

    Allows comma separators (e.g. \"8,000\"). Rejects decimals, scientific notation,
    signs, and empty input. Raises ValueError with WHOLE_KES_MSG on failure.
    """
    if raw is None:
        raise ValueError(WHOLE_KES_MSG)
    s = str(raw).strip()
    if not s:
        raise ValueError(WHOLE_KES_MSG)
    normalized = s.replace(",", "")
    if not normalized.isdigit():
        raise ValueError(WHOLE_KES_MSG)
    return int(normalized)


def max_zero_kes(value) -> int:
    """Non-negative whole KES."""
    z = quantize_kes(value)
    return z if z > 0 else 0


def format_money(value) -> int:
    """Whole-shilling KES as int (SMS, labels, APIs)."""
    return quantize_kes(value)
