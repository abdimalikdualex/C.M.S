"""PDF export for audit trail (ReportLab, A4)."""
from __future__ import annotations

from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape

from django.conf import settings
from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .models import AuditLog


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


def build_audit_trail_pdf(rows: list[AuditLog], *, college_name: str, filters_note: str) -> bytes:
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
    story.append(Paragraph(_safe(f"{college_name} — Audit trail"), styles["Title"]))
    story.append(
        Paragraph(
            _safe(f"Generated {timezone.localtime():%Y-%m-%d %H:%M} · Rows: {len(rows)}"),
            styles["Normal"],
        )
    )
    if filters_note:
        story.append(Paragraph(_safe(f"Filters: {filters_note}"), styles["Normal"]))
    story.append(Spacer(1, 4 * mm))

    header = ["When", "User", "Role", "Module", "Action", "Activity", "Target", "IP"]
    data = [[_safe(h) for h in header]]
    for r in rows:
        data.append(
            [
                _safe(r.created_at.strftime("%Y-%m-%d %H:%M")),
                _safe(r.user_name),
                _safe(r.user_role),
                _safe(r.module),
                _safe(r.get_audit_action_display()),
                _safe((r.activity or r.legacy_event or "")[:120]),
                _safe((r.target_record or "")[:80]),
                _safe(r.ip_address or "—"),
            ]
        )
    tbl = Table(
        data,
        colWidths=[26 * mm, 28 * mm, 22 * mm, 24 * mm, 18 * mm, 38 * mm, 38 * mm, 22 * mm],
        repeatRows=1,
    )
    tbl.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2c5282")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 6.5),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    story.append(tbl)
    doc.build(story)
    return buf.getvalue()
