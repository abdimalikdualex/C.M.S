"""Lightweight exam totals and grade bands for ICT Hub results."""
from __future__ import annotations


def result_total(test, exam) -> float:
    return float(test or 0) + float(exam or 0)


def grade_from_total(total: float) -> str:
    """MVP bands: 80+ Distinction, 60–79 Credit, 40–59 Pass, <40 Fail."""
    try:
        t = float(total)
    except (TypeError, ValueError):
        return ""
    if t >= 80:
        return "Distinction"
    if t >= 60:
        return "Credit"
    if t >= 40:
        return "Pass"
    return "Fail"
