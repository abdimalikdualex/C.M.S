"""Completion certificate PDF (ReportLab)."""
from __future__ import annotations

from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape

from django.conf import settings

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer

from .models import Enrollment


def _safe(text: str) -> str:
    return escape(str(text or ""))


def _logo_flowable(max_w_mm=45, max_h_mm=18):
    rel = Path("main_app") / "static" / "dist" / "img" / "elevate_logo.png"
    p = Path(settings.BASE_DIR) / rel
    if not p.is_file():
        return None
    try:
        return Image(str(p), width=max_w_mm * mm, height=max_h_mm * mm, kind="proportional")
    except Exception:
        return None


def build_completion_certificate_pdf(
    enrollment: Enrollment,
    *,
    college_name: str,
    hub_tagline: str,
    college_location: str = "",
) -> bytes:
    """Certificate PDF for one completed enrollment."""
    enr = enrollment
    student_user = enr.student.admin
    learner_name = (student_user.full_name or "").strip() or student_user.get_full_name() or student_user.email
    course = enr.course
    track_label = course.get_skills_track_display() if course.skills_track else ""

    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        rightMargin=22 * mm,
        leftMargin=22 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
    )
    styles = getSampleStyleSheet()
    story = []

    logo = _logo_flowable()
    if logo:
        story.append(logo)
        story.append(Spacer(1, 6 * mm))

    brand = ParagraphStyle(
        "CertBrand",
        parent=styles["Normal"],
        fontSize=11,
        textColor=colors.HexColor("#555555"),
        alignment=1,
        spaceAfter=2,
    )
    title_style = ParagraphStyle(
        "CertTitle",
        parent=styles["Title"],
        fontSize=22,
        spaceBefore=8,
        spaceAfter=14,
        textColor=colors.HexColor("#1a365d"),
        alignment=1,
    )
    body = ParagraphStyle(
        "CertBody",
        parent=styles["Normal"],
        fontSize=12,
        alignment=1,
        spaceAfter=8,
    )
    accent = ParagraphStyle(
        "CertAccent",
        parent=styles["Heading2"],
        fontSize=16,
        alignment=1,
        spaceBefore=6,
        spaceAfter=16,
        textColor=colors.HexColor("#2c5282"),
    )
    small = ParagraphStyle(
        "CertSmall",
        parent=styles["Normal"],
        fontSize=9,
        alignment=1,
        textColor=colors.HexColor("#666666"),
    )

    story.append(Paragraph(_safe(college_name), brand))
    story.append(Paragraph(_safe(hub_tagline), brand))
    if college_location:
        story.append(Paragraph(_safe(college_location), brand))
    story.append(Spacer(1, 10 * mm))
    story.append(Paragraph("<b>Certificate of completion</b>", title_style))
    story.append(Paragraph("This certifies that", body))
    story.append(Paragraph(f"<b>{_safe(learner_name)}</b>", accent))
    story.append(
        Paragraph("has successfully completed practical ICT training in", body),
    )
    story.append(Paragraph(f"<b>{_safe(course.name)}</b>", accent))
    if track_label and track_label != "General ICT / mixed":
        story.append(Paragraph(_safe(f"Skills track: {track_label}"), body))
    story.append(
        Paragraph(_safe(f"Intake / session: {enr.session.intake_label}"), body),
    )
    if enr.completed_on:
        story.append(
            Paragraph(
                _safe(f"Completion date: {enr.completed_on.strftime('%B %d, %Y')}"),
                body,
            ),
        )
    story.append(Spacer(1, 12 * mm))
    sid = enr.student.student_id or f"id-{enr.student.pk}"
    story.append(
        Paragraph(_safe(f"Learner reference: {sid} · Record enrolment #{enr.pk}"), small),
    )
    doc.build(story)
    return buf.getvalue()
