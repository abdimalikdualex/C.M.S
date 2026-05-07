"""
Server-side PDF generation for receipts and fee statements (ReportLab).
"""
from __future__ import annotations

from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape

from django.conf import settings
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .money import quantize_kes


def _kes_display(value) -> str:
    return f"{quantize_kes(value):,}"


def _safe_para(text: str) -> str:
    return escape(str(text or ""))


def _logo_flowable(max_w_mm=45, max_h_mm=18):
    """Optional ELEVATE logo for PDF header; returns None if file missing."""
    rel = Path("main_app") / "static" / "dist" / "img" / "elevate_logo.png"
    p = Path(settings.BASE_DIR) / rel
    if not p.is_file():
        return None
    try:
        return Image(str(p), width=max_w_mm * mm, height=max_h_mm * mm, kind="proportional")
    except Exception:
        return None


def _doc_header(story, college_name: str, hub_tagline: str, college_location: str = ""):
    logo = _logo_flowable()
    if logo is not None:
        story.append(logo)
        story.append(Spacer(1, 4 * mm))
    styles = getSampleStyleSheet()
    title = ParagraphStyle(
        "BrandTitle",
        parent=styles["Heading1"],
        fontSize=14,
        spaceAfter=4,
        textColor=colors.HexColor("#1a1a1a"),
    )
    sub = ParagraphStyle(
        "BrandSub",
        parent=styles["Normal"],
        fontSize=10,
        spaceAfter=2,
        textColor=colors.HexColor("#444444"),
    )
    story.append(Paragraph(_safe_para(college_name), title))
    story.append(Paragraph(_safe_para(hub_tagline), sub))
    if college_location:
        story.append(Paragraph(_safe_para(college_location), sub))


def build_payment_receipt_pdf(
    payment,
    student,
    college_name: str,
    hub_tagline: str,
    college_location: str = "",
) -> bytes:
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
    )
    story = []
    _doc_header(story, college_name, hub_tagline, college_location)
    styles = getSampleStyleSheet()
    story.append(Paragraph("<b>Payment receipt</b>", styles["Heading2"]))
    story.append(Spacer(1, 6 * mm))

    course_name = "—"
    if payment.enrollment_id:
        course_name = payment.enrollment.course.name
    elif payment.course_id:
        course_name = payment.course.name
    elif student.course_id:
        course_name = student.course.name

    rows = [
        ["Receipt no.", payment.receipt_no or "—"],
        ["Date", payment.paid_at.strftime("%Y-%m-%d %H:%M") if payment.paid_at else "—"],
        ["Student", student.admin.get_full_name()],
        ["Student ID", student.student_id or "—"],
        ["Course", course_name],
    ]
    if payment.enrollment_id:
        rows.append(["Enrollment start", payment.enrollment.start_date.strftime("%Y-%m-%d")])
    rows.extend(
        [
            ["Amount (KES)", _kes_display(payment.amount)],
            ["Mode", payment.get_mode_display()],
        ]
    )
    if payment.reference:
        rows.append(["Reference", payment.reference])
    if payment.note:
        rows.append(["Note", payment.note])
    if payment.created_by_id:
        rows.append(["Recorded by", payment.created_by.get_full_name()])

    data = [
        [
            Paragraph(f"<b>{_safe_para(a)}</b>", styles["Normal"]),
            Paragraph(_safe_para(b), styles["Normal"]),
        ]
        for a, b in rows
    ]
    t = Table(data, colWidths=[45 * mm, 115 * mm])
    t.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LINEBELOW", (0, 0), (-1, -2), 0.5, colors.HexColor("#eeeeee")),
                ("LINEBELOW", (0, -1), (-1, -1), 0.5, colors.HexColor("#cccccc")),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.append(t)
    doc.build(story)
    buf.seek(0)
    return buf.read()


def build_fee_statement_pdf(
    student,
    enrollments,
    payments,
    total_due: int,
    total_paid: int,
    balance: int,
    college_name: str,
    hub_tagline: str,
    college_location: str = "",
) -> bytes:
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
    )
    story = []
    _doc_header(story, college_name, hub_tagline, college_location)
    styles = getSampleStyleSheet()
    story.append(Paragraph("<b>Fee account statement</b>", styles["Heading2"]))
    story.append(Spacer(1, 4 * mm))

    sid = student.student_id or "—"
    course_line = ""
    if getattr(student, "course_id", None) and getattr(student, "course", None):
        course_line = f"Course: {_safe_para(student.course.name)}<br/>"
    enr = ""
    ed = getattr(student, "enrollment_date", None)
    if ed:
        enr = f"Enrolled: {ed.strftime('%Y-%m-%d')}<br/>"
    block = (
        f"<b>{_safe_para(student.admin.get_full_name())}</b><br/>"
        f"Student ID: {_safe_para(sid)}<br/>{course_line}{enr}"
    )
    story.append(Paragraph(block, styles["Normal"]))
    story.append(Spacer(1, 6 * mm))

    summary = Table(
        [
            ["Total course fee (KES)", _kes_display(total_due)],
            ["Total paid (KES)", _kes_display(total_paid)],
            ["Balance (KES)", _kes_display(balance)],
        ],
        colWidths=[80 * mm, 80 * mm],
    )
    summary.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("BACKGROUND", (0, 0), (-1, -2), colors.HexColor("#f5f5f5")),
                ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    story.append(summary)
    story.append(Spacer(1, 8 * mm))

    story.append(Paragraph("<b>Enrollments</b>", styles["Heading3"]))
    enr_header = ["Course", "Start", "Total fee", "Paid", "Balance", "Status"]
    enr_data = [enr_header]
    for e in enrollments:
        enr_data.append(
            [
                e.course.name,
                e.start_date.strftime("%Y-%m-%d") if e.start_date else "—",
                _kes_display(e.total_fee),
                _kes_display(e.amount_paid),
                _kes_display(e.balance_due),
                e.get_status_display(),
            ]
        )
    if len(enr_data) == 1:
        enr_data.append(["No enrollments yet.", "", "", "", "", ""])
    t1 = Table(
        [[Paragraph(_safe_para(c), styles["Normal"]) for c in row] for row in enr_data],
        repeatRows=1,
    )
    t1.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e9ecef")),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    story.append(t1)
    story.append(Spacer(1, 8 * mm))

    story.append(Paragraph("<b>Payments</b>", styles["Heading3"]))
    pay_header = ["Date", "Course", "Receipt", "Amount", "Mode", "Reference"]
    pay_data = [pay_header]
    for p in payments:
        cname = "—"
        if p.enrollment_id:
            cname = p.enrollment.course.name
        elif p.course_id:
            cname = p.course.name
        pay_data.append(
            [
                p.paid_at.strftime("%Y-%m-%d") if p.paid_at else "—",
                cname,
                p.receipt_no or "—",
                _kes_display(p.amount),
                p.get_mode_display(),
                p.reference or "—",
            ]
        )
    if len(pay_data) == 1:
        pay_data.append(["No payments recorded.", "", "", "", "", ""])
    t2 = Table(
        [[Paragraph(_safe_para(c), styles["Normal"]) for c in row] for row in pay_data],
        repeatRows=1,
    )
    t2.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e9ecef")),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    story.append(t2)

    doc.build(story)
    buf.seek(0)
    return buf.read()
