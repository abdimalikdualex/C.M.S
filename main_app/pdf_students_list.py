"""Superadmin student register PDF (ReportLab, A4, branded header)."""
from __future__ import annotations

from io import BytesIO
from pathlib import Path

from django.conf import settings
from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .datetime_display import format_dt
from .student_export_utils import enrollment_row_cells, group_students_for_pdf, student_row_cells

# A4 width 210mm — sum(colWidths) must fit inside page minus left/right margins or ReportLab
# scales the table down (small, cramped text).
_STUDENT_MARGINS_LR_MM = (12, 12)


def _table_comfort_style(*, body_font: float = 8, header_font: float = 8.5) -> list:
    """Readable padding and typography for register tables."""
    return [
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("FONTSIZE", (0, 0), (-1, 0), header_font),
        ("FONTSIZE", (0, 1), (-1, -1), body_font),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2c5282")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#a8a8a8")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f4f6f8")]),
    ]


def _safe_xml(s: str) -> str:
    from xml.sax.saxutils import escape

    return escape(str(s or ""))


def _cell_paragraph(text: str, *, font_size: float = 8, leading: float | None = None) -> Paragraph:
    """Table body cell with wrapping (column width from Table colWidths)."""
    ld = leading if leading is not None else round(font_size * 1.25, 1)
    st = ParagraphStyle(
        "RegCellPara",
        fontName="Helvetica",
        fontSize=font_size,
        leading=ld,
        alignment=0,
    )
    return Paragraph(_safe_xml(text), st)


def _logo_flowable(max_w_mm=45, max_h_mm=18):
    rel = Path("main_app") / "static" / "dist" / "img" / "elevate_logo.png"
    p = Path(settings.BASE_DIR) / rel
    if not p.is_file():
        return None
    try:
        return Image(str(p), width=max_w_mm * mm, height=max_h_mm * mm, kind="proportional")
    except Exception:
        return None


def _brand_header_story(story, college_name: str, system_title: str, subtitle: str = "", location: str = ""):
    logo = _logo_flowable()
    if logo:
        story.append(logo)
        story.append(Spacer(1, 4 * mm))
    styles = getSampleStyleSheet()
    title_st = ParagraphStyle(
        "DocTitle",
        parent=styles["Heading1"],
        fontSize=14,
        spaceAfter=4,
        textColor=colors.HexColor("#1a365d"),
        alignment=1,
    )
    sub_st = ParagraphStyle(
        "DocSub",
        parent=styles["Normal"],
        fontSize=10,
        spaceAfter=2,
        textColor=colors.HexColor("#444444"),
        alignment=1,
    )
    small_st = ParagraphStyle(
        "DocSmall",
        parent=styles["Normal"],
        fontSize=8,
        textColor=colors.HexColor("#666666"),
        alignment=1,
    )
    story.append(Paragraph(_safe_xml(system_title), title_st))
    story.append(Paragraph(_safe_xml(college_name), sub_st))
    if subtitle:
        story.append(Paragraph(_safe_xml(subtitle), sub_st))
    if location:
        story.append(Paragraph(_safe_xml(location), small_st))


def build_student_register_pdf(
    students: list,
    *,
    college_name: str,
    hub_tagline: str,
    college_location: str,
    filters_description: str,
    group_by: str = "",
) -> bytes:
    system_title = f"{college_name} – ICT Hub"
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=_STUDENT_MARGINS_LR_MM[0] * mm,
        rightMargin=_STUDENT_MARGINS_LR_MM[1] * mm,
        topMargin=12 * mm,
        bottomMargin=14 * mm,
    )
    story = []
    _brand_header_story(story, college_name, system_title, hub_tagline, college_location)
    story.append(Spacer(1, 4 * mm))
    styles = getSampleStyleSheet()
    story.append(Paragraph("<b>Student list register</b>", styles["Heading2"]))
    gen_st = ParagraphStyle("Gen", parent=styles["Normal"], fontSize=9, spaceAfter=2)
    story.append(
        Paragraph(
            _safe_xml(f"Generated: {format_dt(timezone.now())} · Total records: {len(students)}"),
            gen_st,
        )
    )
    story.append(Paragraph(_safe_xml(f"Filters: {filters_description}"), gen_st))
    story.append(Spacer(1, 4 * mm))

    header = [
        "Admission no.",
        "Full name",
        "Phone",
        "Course",
        "Session",
        "Enrol. date",
        "Fee status",
    ]
    # Usable width 210 - 12 - 12 = 186mm (must match sum of colWidths exactly)
    col_w = [
        20 * mm,  # Admission no.
        42 * mm,  # Full name
        23 * mm,  # Phone
        32 * mm,  # Course
        28 * mm,  # Session
        18 * mm,  # Enrol. date
        23 * mm,  # Fee status
    ]

    gb = (group_by or "").strip()
    groups = group_students_for_pdf(students, gb) if gb in ("course", "session") else [("", students)]

    for idx, (label, group) in enumerate(groups):
        if label:
            story.append(Paragraph(f"<b>{_safe_xml(label)}</b> ({len(group)} learner{'s' if len(group) != 1 else ''})", gen_st))
            story.append(Spacer(1, 2 * mm))
        data = [[_safe_xml(h) for h in header]]
        for st in group:
            data.append([_cell_paragraph(c, font_size=8) for c in student_row_cells(st)])
        tbl = Table(data, colWidths=col_w, repeatRows=1)
        tbl.setStyle(TableStyle(_table_comfort_style(body_font=8, header_font=8.5)))
        story.append(tbl)
        if idx < len(groups) - 1:
            story.append(Spacer(1, 6 * mm))

    doc.build(story)
    return buf.getvalue()


def build_enrollment_register_pdf(
    enrollments: list,
    *,
    college_name: str,
    hub_tagline: str,
    college_location: str,
    filters_description: str,
) -> bytes:
    system_title = f"{college_name} – ICT Hub"
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=12 * mm,
        rightMargin=12 * mm,
        topMargin=12 * mm,
        bottomMargin=14 * mm,
    )
    story = []
    _brand_header_story(story, college_name, system_title, hub_tagline, college_location)
    story.append(Spacer(1, 4 * mm))
    styles = getSampleStyleSheet()
    story.append(Paragraph("<b>Enrollment register</b>", styles["Heading2"]))
    gen_st = ParagraphStyle("Gen", parent=styles["Normal"], fontSize=9, spaceAfter=2)
    story.append(
        Paragraph(
            _safe_xml(f"Generated: {format_dt(timezone.now())} · Total rows: {len(enrollments)}"),
            gen_st,
        )
    )
    story.append(Paragraph(_safe_xml(f"Filters: {filters_description}"), gen_st))
    story.append(Spacer(1, 4 * mm))

    header = [
        "Admission no.",
        "Full name",
        "Phone",
        "Course",
        "Session",
        "Start",
        "Status",
        "Fee",
    ]
    # Usable width 210 - 12 - 12 = 186mm
    col_w = [
        17 * mm,
        35 * mm,
        19 * mm,
        28 * mm,
        26 * mm,
        16 * mm,
        16 * mm,
        29 * mm,
    ]
    data = [[_safe_xml(h) for h in header]]
    for enr in enrollments:
        data.append([_cell_paragraph(c, font_size=7.5) for c in enrollment_row_cells(enr)])
    tbl = Table(data, colWidths=col_w, repeatRows=1)
    tbl.setStyle(TableStyle(_table_comfort_style(body_font=7.5, header_font=8)))
    story.append(tbl)
    doc.build(story)
    return buf.getvalue()
