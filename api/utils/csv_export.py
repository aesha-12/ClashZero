"""
╔══════════════════════════════════════════════════════════════╗
║         ClashZero — AI Exam Timetable Generator              ║
║         utils/csv_export.py · CSV Byte Builder               ║
║         Member 2: Engine Room (Backend & API)                ║
╚══════════════════════════════════════════════════════════════╝

Responsibilities:
  - Convert a List[ScheduledSlot] into a UTF-8 CSV byte string
  - Sort schedule by day → slot for human readability
  - Prepend a UTF-8 BOM so Excel on Windows opens it correctly
  - Inject a metadata header block (title, generated timestamp)
  - Use friendly display headers (not raw field names)
  - Group rows visually by day with blank separator rows

Output structure:
  ┌─────────────────────────────────────────┐
  │  # ClashZero Exam Timetable             │
  │  # Generated: 2025-01-15 10:30:00       │
  │  # Total Exams: 8                       │
  │  (blank row)                            │
  │  Day | Slot | Schedule | ... (headers)  │
  │  1   | 1    | Day 1 – Morning | ...     │
  │  1   | 2    | Day 1 – Afternoon | ...   │
  │  (blank separator between days)         │
  │  2   | 1    | Day 2 – Morning | ...     │
  └─────────────────────────────────────────┘

Public API:
  build_csv_bytes(schedule) → bytes
"""

from __future__ import annotations

import csv
import io
import logging
from datetime import datetime
from typing import Dict, List

from api.models import ScheduledSlot

logger = logging.getLogger("clashzero.csv_export")


# ════════════════════════════════════════════════════════════════
# CONSTANTS
# ════════════════════════════════════════════════════════════════

# Ordered column keys (must match ScheduledSlot field names)
_COLUMNS: List[str] = [
    "day",
    "slot",
    "slot_label",
    "subject_id",
    "subject_name",
    "duration",
    "student_count",
]

# Human-readable header row displayed in the CSV file
_DISPLAY_HEADERS: Dict[str, str] = {
    "day":           "Day",
    "slot":          "Slot",
    "slot_label":    "Schedule",
    "subject_id":    "Subject Code",
    "subject_name":  "Subject Name",
    "duration":      "Duration (min)",
    "student_count": "No. of Students",
}

# Column widths hint (informational — not enforced in plain CSV)
# Useful if this output is later post-processed into a spreadsheet
_COLUMN_NOTES: Dict[str, str] = {
    "day":           "Exam day number (1-indexed)",
    "slot":          "Slot within the day (1-indexed)",
    "slot_label":    "Human-readable time slot",
    "subject_id":    "Unique subject code",
    "subject_name":  "Full subject name",
    "duration":      "Exam duration in minutes",
    "student_count": "Number of enrolled students",
}


# ════════════════════════════════════════════════════════════════
# INTERNAL HELPERS
# ════════════════════════════════════════════════════════════════

def _write_metadata_block(writer: csv.writer, schedule: List[ScheduledSlot]) -> None:
    """
    Write a comment-style metadata block at the top of the CSV.

    Uses '#' prefix on each row — Excel and most CSV parsers
    treat unknown leading characters as plain text, so this
    does not break the data section below.

    Parameters
    ----------
    writer   : csv.writer  — active writer bound to the output buffer
    schedule : list        — used to compute summary statistics
    """
    total_exams   = len(schedule)
    total_days    = max(s.day for s in schedule)
    total_students = sum(s.student_count for s in schedule)
    generated_at  = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    metadata_rows = [
        ["# ClashZero — Exam Timetable Export"],
        [f"# Generated : {generated_at}"],
        [f"# Total Exams      : {total_exams}"],
        [f"# Days Used        : {total_days}"],
        [f"# Total Enrollments: {total_students}"],
        [],   # blank separator before headers
    ]

    for row in metadata_rows:
        writer.writerow(row)


def _write_header_row(writer: csv.writer) -> None:
    """
    Write the friendly column header row.

    Uses display names from _DISPLAY_HEADERS so the exported
    file is immediately readable without knowing field names.
    """
    writer.writerow([_DISPLAY_HEADERS[col] for col in _COLUMNS])


def _slot_to_row(entry: ScheduledSlot) -> List[str]:
    """
    Convert a single ScheduledSlot to an ordered list of string values
    matching the _COLUMNS order.

    Parameters
    ----------
    entry : ScheduledSlot

    Returns
    -------
    List[str]
        One CSV data row.
    """
    return [str(getattr(entry, col)) for col in _COLUMNS]


def _write_schedule_rows(
    writer: csv.writer,
    schedule: List[ScheduledSlot],
) -> None:
    """
    Write all schedule entries grouped by day.

    A blank separator row is inserted between each day group
    to improve visual readability when opened in spreadsheet apps.

    Parameters
    ----------
    writer   : csv.writer
    schedule : List[ScheduledSlot]  — already sorted by (day, slot)
    """
    current_day: int | None = None

    for entry in schedule:
        # Insert blank row between day groups (not before the first group)
        if current_day is not None and entry.day != current_day:
            writer.writerow([])   # visual day separator

        writer.writerow(_slot_to_row(entry))
        current_day = entry.day


# ════════════════════════════════════════════════════════════════
# PUBLIC API
# ════════════════════════════════════════════════════════════════

def build_csv_bytes(schedule: List[ScheduledSlot]) -> bytes:
    """
    Serialise a timetable schedule to UTF-8 CSV bytes.

    Structure
    ---------
    1. UTF-8 BOM          → Excel on Windows opens without encoding prompt
    2. Metadata block     → title, timestamp, summary stats (# prefixed)
    3. Blank separator    → visual gap before data
    4. Header row         → friendly display column names
    5. Data rows          → one row per ScheduledSlot, sorted day → slot
       (blank row between each day group for readability)

    Parameters
    ----------
    schedule : List[ScheduledSlot]
        The generated exam schedule to export.
        Must contain at least one entry.

    Returns
    -------
    bytes
        Raw CSV bytes ready for HTTP streaming.
        Encoded as UTF-8 with BOM prefix (\ufeff).

    Raises
    ------
    ValueError
        If schedule is empty — callers should validate before calling.

    Examples
    --------
    >>> csv_bytes = build_csv_bytes(response.schedule)
    >>> open("timetable.csv", "wb").write(csv_bytes)
    """
    if not schedule:
        raise ValueError(
            "Cannot build CSV from an empty schedule. "
            "Ensure the timetable was generated successfully."
        )

    # ── Sort: day ascending, then slot ascending ─────────────────
    sorted_schedule = sorted(schedule, key=lambda s: (s.day, s.slot))

    # ── Build CSV in memory ──────────────────────────────────────
    # Use StringIO first (csv.writer works on text), then encode at the end
    buffer = io.StringIO()

    writer = csv.writer(
        buffer,
        dialect      = "excel",      # CRLF line endings — standard for CSV
        quoting      = csv.QUOTE_MINIMAL,
    )

    # Write sections
    _write_metadata_block(writer, sorted_schedule)
    _write_header_row(writer)
    _write_schedule_rows(writer, sorted_schedule)

    # ── Encode with BOM ──────────────────────────────────────────
    # \ufeff is the UTF-8 BOM — prepended as a string before encoding
    # so the BOM is part of the UTF-8 byte sequence (EF BB BF)
    csv_text  = buffer.getvalue()
    csv_bytes = ("\ufeff" + csv_text).encode("utf-8")

    logger.debug(
        f"CSV built: {len(sorted_schedule)} rows, "
        f"{len(csv_bytes):,} bytes."
    )

    return csv_bytes
