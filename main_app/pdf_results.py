"""PDF exports for exam / unit results (ReportLab, branded)."""
from __future__ import annotations

from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape

from django.conf import settings
from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .models import Student


def _safe(s: str) -> str:
    return escape(str(s or ""))


def _logo_flowable(max_w_mm=40, max_h_mm=16):
    rel = Path("main_app") / "static" / "dist" / "img" / "elevate_logo.png"
    p = Path(settings.BASE_DIR) / rel
    if not p.is_file():
        return None
    try:
        return Image(str(p), width=max_w_mm * mm, height=max_h_mm * mm, kind="proportional")
    except Exception:
        return None


def build_results_register_pdf(
    rows: list,
    *,
    college_name: str,
    hub_tagline: str,
    college_location: str = "",
    title: str = "Exam results",
) -> bytes:
    """rows: StudentResult queryset or list with select_related."""
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=14 * mm,
        rightMargin=14 * mm,
        topMargin=12 * mm,
        bottomMargin=12 * mm,
    )
    story = []
    logo = _logo_flowable()
    if logo:
        story.append(logo)
        story.append(Spacer(1, 3 * mm))
    styles = getSampleStyleSheet()
    story.append(Paragraph(_safe(title), styles["Title"]))
    story.append(
        Paragraph(
            _safe(f"{college_name} — {hub_tagline}"),
            styles["Normal"],
        )
    )
    if college_location:
        story.append(Paragraph(_safe(college_location), styles["Normal"]))
    story.append(
        Paragraph(
            _safe(f"Generated: {timezone.localtime():%Y-%m-%d %H:%M} · Rows: {len(rows)}"),
            styles["Normal"],
        )
    )
    story.append(Spacer(1, 4 * mm))

    header = ["Admission", "Name", "Course", "Unit", "Test", "Exam", "Total", "Grade", "Remarks"]
    data = [[_safe(h) for h in header]]
    for r in rows:
        data.append(
            [
                _safe(r.student.student_id),
                _safe(r.student.admin.get_full_name())[:28],
                _safe(r.subject.course.name if r.subject.course_id else "")[:22],
                _safe(r.subject.name)[:26],
                _safe(r.test),
                _safe(r.exam),
                _safe(f"{r.total_score():.1f}"),
                _safe(r.grade),
                _safe((r.remarks or "")[:40]),
            ]
        )
    tbl = Table(
        data,
        colWidths=[20 * mm, 32 * mm, 24 * mm, 28 * mm, 12 * mm, 12 * mm, 14 * mm, 20 * mm, 34 * mm],
        repeatRows=1,
    )
    tbl.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2c5282")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                ("FONTSIZE", (0, 0), (-1, -1), 6.5),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    story.append(tbl)
    doc.build(story)
    return buf.getvalue()


def build_student_result_slip_pdf(
    student: Student,
    result_rows: list,
    *,
    college_name: str,
    hub_tagline: str,
    college_location: str = "",
) -> bytes:
    """result_rows: list of dicts with keys unit_name, course_name, test, exam, total, grade, remarks."""
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=14 * mm,
        bottomMargin=14 * mm,
    )
    story = []
    logo = _logo_flowable(42, 16)
    if logo:
        story.append(logo)
        story.append(Spacer(1, 4 * mm))
    styles = getSampleStyleSheet()
    story.append(Paragraph(_safe("Result slip"), styles["Title"]))
    story.append(Paragraph(_safe(college_name), styles["Heading3"]))
    story.append(Paragraph(_safe(hub_tagline), styles["Normal"]))
    if college_location:
        story.append(Paragraph(_safe(college_location), styles["Normal"]))
    story.append(Spacer(1, 6 * mm))
    adm = (student.student_id or "").strip() or f"id-{student.pk}"
    nm = student.admin.get_full_name()
    block = (
        f"<b>{_safe(nm)}</b><br/>"
        f"Admission no.: {_safe(adm)}<br/>"
        f"Generated: {_safe(timezone.localtime().strftime('%Y-%m-%d %H:%M'))}"
    )
    story.append(Paragraph(block, styles["Normal"]))
    story.append(Spacer(1, 5 * mm))

    header = ["Course", "Unit / subject", "Test", "Exam", "Total", "Grade", "Remarks"]
    data = [[_safe(h) for h in header]]
    for row in result_rows:
        data.append(
            [
                _safe(row.get("course_name", ""))[:24],
                _safe(row.get("unit_name", ""))[:28],
                _safe(row.get("test", "")),
                _safe(row.get("exam", "")),
                _safe(row.get("total", "")),
                _safe(row.get("grade", "")),
                _safe((row.get("remarks") or "")[:36]),
            ]
        )
    tbl = Table(
        data,
        colWidths=[28 * mm, 38 * mm, 14 * mm, 14 * mm, 16 * mm, 22 * mm, 44 * mm],
        repeatRows=1,
    )
    tbl.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2c5282")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    story.append(tbl)
    doc.build(story)
    return buf.getvalue()
