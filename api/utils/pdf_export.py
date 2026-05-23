"""
╔══════════════════════════════════════════════════════════════╗
║         ClashZero — AI Exam Timetable Generator              ║
║         utils/pdf_export.py · ReportLab PDF Builder          ║
║         Member 2: Engine Room (Backend & API)                ║
╚══════════════════════════════════════════════════════════════╝

Responsibilities:
  - Convert a List[ScheduledSlot] into a formatted PDF document
  - Render a branded header, stats bar, colour-coded table, legend
  - Stream-safe: returns raw bytes (no temp files written to disk)
  - Page footer with page numbers on every page

Document layout (Landscape A4):
  ┌──────────────────────────────────────────────────────────┐
  │  ClashZero                                               │
  │  [title]                                  [timestamp]    │
  │  ══════════════════════════════════════════════════════  │
  │  Total Exams: 8   Days Used: 3   Enrollments: 240        │
  │                                                          │
  │  ┌─────┬──────┬────────────┬────────┬──────────┬─────┐  │
  │  │ Day │ Slot │ Schedule   │ Code   │ Name     │ ... │  │
  │  ├─────┼──────┼────────────┼────────┼──────────┼─────┤  │
  │  │  1  │  1   │ Day 1–Morn │ CS101  │ Data Str │ ... │  │
  │  │  1  │  2   │ Day 1–Aftn │ MA201  │ Lin Alg  │ ... │  │
  │  └─────┴──────┴────────────┴────────┴──────────┴─────┘  │
  │                                                          │
  │  Legend: ■ Morning  ■ Afternoon  ■ Evening               │
  │  ─────────────────────────────────────────────────────── │
  │  ClashZero Exam Timetable  |  Page 1                     │
  └──────────────────────────────────────────────────────────┘

Public API:
  build_pdf_bytes(schedule, title) → bytes
"""

from __future__ import annotations

import io
import logging
from datetime import datetime
from typing import List

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    HRFlowable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from api.models import ScheduledSlot

logger = logging.getLogger("clashzero.pdf_export")


# ════════════════════════════════════════════════════════════════
# BRAND COLOURS
# ════════════════════════════════════════════════════════════════

class Brand:
    """
    ClashZero colour palette.
    Centralised here so any redesign touches one place only.
    """
    DARK        = colors.HexColor("#1A1A2E")   # Deep navy  — table header bg
    ACCENT      = colors.HexColor("#E94560")   # Red accent — title underline
    HEADER_TEXT = colors.white
    BODY_TEXT   = colors.HexColor("#1A1A2E")
    SUBTEXT     = colors.HexColor("#555555")
    GRID        = colors.HexColor("#D1D9E6")   # Table grid lines
    ROW_EVEN    = colors.HexColor("#F7F9FC")   # Alternating row (even)
    ROW_ODD     = colors.white                  # Alternating row (odd)
    FOOTER      = colors.HexColor("#888888")


# Slot number → background colour for the slot column cells
_SLOT_COLOURS = {
    1: colors.HexColor("#D0EAFF"),   # Morning   — pale blue
    2: colors.HexColor("#FFF3CD"),   # Afternoon — pale amber
    3: colors.HexColor("#D4EDDA"),   # Evening   — pale green
    4: colors.HexColor("#F3D9FA"),   # Late Eve  — pale purple
    5: colors.HexColor("#FFE5D9"),   # Night     — pale orange
    6: colors.HexColor("#E2E3E5"),   # Late Night — pale grey
}
_DEFAULT_SLOT_COLOUR = colors.HexColor("#E8E8E8")

# Slot number → legend label
_SLOT_LABELS = {
    1: "Morning",
    2: "Afternoon",
    3: "Evening",
    4: "Late Evening",
    5: "Night",
    6: "Late Night",
}

# Slot number → hex string for legend coloured squares
_SLOT_HEX = {
    1: "#5BA4CF",
    2: "#E6AC00",
    3: "#27AE60",
    4: "#9B59B6",
    5: "#E67E22",
    6: "#7F8C8D",
}


# ════════════════════════════════════════════════════════════════
# PARAGRAPH STYLES
# ════════════════════════════════════════════════════════════════

def _build_styles() -> dict:
    """
    Build and return all named paragraph styles used in the document.
    Isolated here to keep the story builder functions clean.

    Returns
    -------
    dict
        Keys are style names; values are ParagraphStyle instances.
    """
    base = getSampleStyleSheet()

    return {
        "doc_title": ParagraphStyle(
            "DocTitle",
            parent    = base["Title"],
            fontName  = "Helvetica-Bold",
            fontSize  = 22,
            textColor = Brand.DARK,
            spaceAfter= 2,
            leading   = 26,
        ),
        "doc_subtitle": ParagraphStyle(
            "DocSubtitle",
            parent    = base["Normal"],
            fontName  = "Helvetica",
            fontSize  = 8,
            textColor = Brand.SUBTEXT,
            spaceAfter= 10,
        ),
        "stats": ParagraphStyle(
            "Stats",
            parent    = base["Normal"],
            fontName  = "Helvetica",
            fontSize  = 9,
            textColor = Brand.SUBTEXT,
            spaceAfter= 14,
        ),
        "legend_heading": ParagraphStyle(
            "LegendHeading",
            parent    = base["Normal"],
            fontName  = "Helvetica-Bold",
            fontSize  = 8,
            textColor = Brand.BODY_TEXT,
            spaceBefore=6,
            spaceAfter= 3,
        ),
        "legend_item": ParagraphStyle(
            "LegendItem",
            parent    = base["Normal"],
            fontName  = "Helvetica",
            fontSize  = 8,
            textColor = Brand.SUBTEXT,
            spaceAfter= 2,
        ),
    }


# ════════════════════════════════════════════════════════════════
# TABLE BUILDER
# ════════════════════════════════════════════════════════════════

# Column definitions: (field_name, display_header, width_cm)
_TABLE_COLUMNS = [
    ("day",           "Day",            1.8),
    ("slot",          "Slot",           1.5),
    ("slot_label",    "Schedule",       5.5),
    ("subject_id",    "Subject Code",   3.5),
    ("subject_name",  "Subject Name",   7.0),
    ("duration",      "Duration (min)", 3.5),
    ("student_count", "Students",       2.5),
]


def _build_table(schedule: List[ScheduledSlot]) -> Table:
    """
    Build the main schedule Table flowable.

    Design decisions:
    - Header row: dark navy background, white bold text
    - Data rows: alternating white / light-grey for readability
    - Slot column (col 2): colour-coded by slot number
      (Morning=blue, Afternoon=amber, Evening=green, …)
    - repeatRows=1: header repeats on every page for long timetables
    - Grid lines: light grey to avoid visual noise

    Parameters
    ----------
    schedule : List[ScheduledSlot]
        Already sorted by (day, slot).

    Returns
    -------
    Table
        ReportLab Table flowable ready to append to the story.
    """
    # ── Build data rows ──────────────────────────────────────────
    headers   = [col[1] for col in _TABLE_COLUMNS]
    col_widths = [col[2] * cm for col in _TABLE_COLUMNS]

    table_data = [headers]   # Row 0 = header

    for entry in schedule:
        row = [str(getattr(entry, col[0])) for col in _TABLE_COLUMNS]
        table_data.append(row)

    # ── Base table style ─────────────────────────────────────────
    style_commands = [
        # ── Header row (row 0) ──────────────────────────────────
        ("BACKGROUND",    (0, 0), (-1, 0),  Brand.DARK),
        ("TEXTCOLOR",     (0, 0), (-1, 0),  Brand.HEADER_TEXT),
        ("FONTNAME",      (0, 0), (-1, 0),  "Helvetica-Bold"),
        ("FONTSIZE",      (0, 0), (-1, 0),  9),
        ("ALIGN",         (0, 0), (-1, 0),  "CENTER"),
        ("TOPPADDING",    (0, 0), (-1, 0),  10),
        ("BOTTOMPADDING", (0, 0), (-1, 0),  10),
        # Accent underline below header
        ("LINEBELOW",     (0, 0), (-1, 0),  1.5, Brand.ACCENT),

        # ── Data rows (row 1 onwards) ────────────────────────────
        ("FONTNAME",      (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE",      (0, 1), (-1, -1), 8),
        ("TOPPADDING",    (0, 1), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 1), (-1, -1), 7),
        ("LEFTPADDING",   (0, 0), (-1, -1), 8),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 8),

        # ── Alignment ────────────────────────────────────────────
        ("ALIGN",         (0, 1), (1, -1),  "CENTER"),   # Day, Slot centered
        ("ALIGN",         (2, 1), (-1, -1), "LEFT"),     # rest left-aligned
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),

        # ── Grid ─────────────────────────────────────────────────
        ("GRID",          (0, 0), (-1, -1), 0.5, Brand.GRID),
        ("BOX",           (0, 0), (-1, -1), 1.2, Brand.DARK),
    ]

    # ── Per-row dynamic styles ───────────────────────────────────
    # Alternating row bg + slot colour on the Schedule column (col 2)
    for row_idx, entry in enumerate(schedule, start=1):
        row_bg    = Brand.ROW_EVEN if row_idx % 2 == 0 else Brand.ROW_ODD
        slot_bg   = _SLOT_COLOURS.get(entry.slot, _DEFAULT_SLOT_COLOUR)

        # Alternating background for full row
        style_commands.append(("BACKGROUND", (0, row_idx), (-1, row_idx), row_bg))

        # Slot colour on Slot (col 1) and Schedule (col 2) cells
        style_commands.append(("BACKGROUND", (1, row_idx), (2, row_idx), slot_bg))

    table = Table(table_data, colWidths=col_widths, repeatRows=1)
    table.setStyle(TableStyle(style_commands))
    return table


# ════════════════════════════════════════════════════════════════
# LEGEND BUILDER
# ════════════════════════════════════════════════════════════════

def _build_legend(
    schedule: List[ScheduledSlot],
    styles: dict,
) -> List:
    """
    Build a colour legend flowable list explaining slot colours.

    Only includes slots that actually appear in the schedule
    (no redundant legend entries for unused slots).

    Parameters
    ----------
    schedule : List[ScheduledSlot]
    styles   : dict  — paragraph styles from _build_styles()

    Returns
    -------
    List of ReportLab flowables.
    """
    used_slots = sorted({entry.slot for entry in schedule})

    flowables = [Paragraph("Slot Colour Legend", styles["legend_heading"])]

    for slot in used_slots:
        hex_colour = _SLOT_HEX.get(slot, "#999999")
        label      = _SLOT_LABELS.get(slot, f"Slot {slot}")
        flowables.append(
            Paragraph(
                f'<font color="{hex_colour}">&#9632;</font>'   # ■ filled square
                f'&nbsp;&nbsp;Slot {slot} — {label}',
                styles["legend_item"],
            )
        )

    return flowables


# ════════════════════════════════════════════════════════════════
# FOOTER CALLBACK
# ════════════════════════════════════════════════════════════════

def _draw_footer(canvas, doc) -> None:
    """
    ReportLab canvas callback — draws a footer on every page.

    Called by SimpleDocTemplate for onFirstPage and onLaterPages.
    Uses saveState / restoreState so it never bleeds into content.

    Renders:
      Left  — "ClashZero Exam Timetable  |  Page N"
      Right — generation timestamp
    """
    canvas.saveState()

    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(Brand.FOOTER)

    # Left: service label + page number
    canvas.drawString(
        doc.leftMargin,
        0.9 * cm,
        f"ClashZero Exam Timetable  |  Page {doc.page}",
    )

    # Right: timestamp
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    canvas.drawRightString(
        doc.width + doc.leftMargin,
        0.9 * cm,
        f"Generated: {timestamp}",
    )

    # Thin rule above footer text
    canvas.setStrokeColor(Brand.GRID)
    canvas.setLineWidth(0.5)
    canvas.line(
        doc.leftMargin,
        1.1 * cm,
        doc.width + doc.leftMargin,
        1.1 * cm,
    )

    canvas.restoreState()


# ════════════════════════════════════════════════════════════════
# STORY BUILDER
# ════════════════════════════════════════════════════════════════

def _build_story(
    schedule: List[ScheduledSlot],
    title: str,
    styles: dict,
) -> list:
    """
    Assemble the complete ReportLab story (list of flowables).

    Order:
    1. Title + subtitle (generation info)
    2. Accent rule
    3. Summary stats bar
    4. Main schedule table
    5. Spacer
    6. Colour legend

    Parameters
    ----------
    schedule : List[ScheduledSlot]  — sorted by (day, slot)
    title    : str                  — document title from request
    styles   : dict                 — paragraph styles

    Returns
    -------
    list of ReportLab Flowable objects.
    """
    story = []

    # ── 1. Title block ───────────────────────────────────────────
    generated_at = datetime.now().strftime("%B %d, %Y at %H:%M")

    story.append(Paragraph(title, styles["doc_title"]))
    story.append(
        Paragraph(
            f"ClashZero AI Timetable Generator &nbsp;|&nbsp; {generated_at}",
            styles["doc_subtitle"],
        )
    )

    # ── 2. Accent rule ───────────────────────────────────────────
    story.append(
        HRFlowable(
            width      = "100%",
            thickness  = 2,
            color      = Brand.ACCENT,
            spaceAfter = 12,
        )
    )

    # ── 3. Summary stats bar ─────────────────────────────────────
    total_exams    = len(schedule)
    total_days     = max(s.day for s in schedule)
    total_students = sum(s.student_count for s in schedule)
    unique_slots   = len({(s.day, s.slot) for s in schedule})

    story.append(
        Paragraph(
            f"<b>Total Exams:</b> {total_exams} &nbsp;&nbsp;&nbsp; "
            f"<b>Days Used:</b> {total_days} &nbsp;&nbsp;&nbsp; "
            f"<b>Unique Slots:</b> {unique_slots} &nbsp;&nbsp;&nbsp; "
            f"<b>Total Enrollments:</b> {total_students:,}",
            styles["stats"],
        )
    )

    # ── 4. Main table ────────────────────────────────────────────
    story.append(_build_table(schedule))
    story.append(Spacer(1, 0.5 * cm))

    # ── 5. Legend ────────────────────────────────────────────────
    story.extend(_build_legend(schedule, styles))

    return story


# ════════════════════════════════════════════════════════════════
# PUBLIC API
# ════════════════════════════════════════════════════════════════

def build_pdf_bytes(
    schedule: List[ScheduledSlot],
    title: str = "Exam Timetable",
) -> bytes:
    """
    Render a timetable schedule as a formatted PDF document.

    The PDF is built entirely in memory — no temp files are written
    to disk, making this safe for concurrent requests.

    Parameters
    ----------
    schedule : List[ScheduledSlot]
        The generated exam schedule to render.
        Must contain at least one entry.
    title : str, optional
        Document title displayed in the PDF header.
        Defaults to 'Exam Timetable'.

    Returns
    -------
    bytes
        Raw PDF bytes starting with '%PDF-' magic bytes,
        ready for HTTP streaming.

    Raises
    ------
    ValueError
        If schedule is empty.

    Examples
    --------
    >>> pdf_bytes = build_pdf_bytes(response.schedule, title="Sem 1 Exams")
    >>> open("timetable.pdf", "wb").write(pdf_bytes)
    """
    if not schedule:
        raise ValueError(
            "Cannot build PDF from an empty schedule. "
            "Ensure the timetable was generated successfully."
        )

    # ── Sort: day → slot ascending ───────────────────────────────
    sorted_schedule = sorted(schedule, key=lambda s: (s.day, s.slot))

    # ── In-memory buffer (no disk I/O) ───────────────────────────
    buffer = io.BytesIO()

    # ── Document template ─────────────────────────────────────────
    doc = SimpleDocTemplate(
        buffer,
        pagesize     = landscape(A4),
        leftMargin   = 1.8 * cm,
        rightMargin  = 1.8 * cm,
        topMargin    = 2.0 * cm,
        bottomMargin = 2.0 * cm,
        title        = title,
        author       = "ClashZero — AI Exam Timetable Generator",
        subject      = "Exam Timetable",
        creator      = "ClashZero API v1.0",
    )

    # ── Build story & render ──────────────────────────────────────
    styles = _build_styles()
    story  = _build_story(sorted_schedule, title, styles)

    doc.build(
        story,
        onFirstPage  = _draw_footer,
        onLaterPages = _draw_footer,
    )

    pdf_bytes = buffer.getvalue()
    buffer.close()

    logger.debug(
        f"PDF built: {len(sorted_schedule)} entries, "
        f"{len(pdf_bytes):,} bytes."
    )

    return pdf_bytes
