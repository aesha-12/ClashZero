"""
╔══════════════════════════════════════════════════════════════╗
║         ClashZero — AI Exam Timetable Generator              ║
║         routes/export.py · CSV & PDF Export Endpoints        ║
║         Member 2: Engine Room (Backend & API)                ║
╚══════════════════════════════════════════════════════════════╝

Responsibilities:
  - Accept a generated schedule payload from the React frontend
  - Stream back a downloadable CSV or PDF file
  - Stateless design — no DB or session required
    (frontend posts the schedule it already has; server renders the file)

Why stateless?
  The frontend already holds the TimetableResponse from /generate.
  Re-posting it here avoids needing a server-side cache or DB lookup,
  making the export endpoints independently testable and horizontally
  scalable with zero shared state.

Flow:
  POST /api/v1/export/csv
  POST /api/v1/export/pdf
        │
        ├─ Pydantic validates ExportPayload
        ├─ Delegates to utils/csv_export.py or utils/pdf_export.py
        └─ Streams bytes back with correct Content-Disposition header
           (triggers browser "Save As" dialog automatically)
"""

from __future__ import annotations

import logging
from typing import List

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from api.models import ScheduledSlot
from api.utils.csv_export import build_csv_bytes
from api.utils.pdf_export import build_pdf_bytes

logger = logging.getLogger("clashzero.export")
router = APIRouter()


# ════════════════════════════════════════════════════════════════
# REQUEST SCHEMA
# ════════════════════════════════════════════════════════════════

class ExportPayload(BaseModel):
    """
    Stateless export request body.

    The frontend posts back the schedule it received from /generate
    along with the timetable_id (used as the download filename).

    No server-side session or database lookup is needed — the full
    schedule travels with the request.

    Fields
    ------
    timetable_id : str
        UUID from the generation response. Used to name the file,
        e.g. 'timetable_a1b2c3d4.pdf'.
    schedule : List[ScheduledSlot]
        The complete list of scheduled exam entries to export.
        Must contain at least one entry.
    title : str
        Document title displayed in the PDF header.
        Ignored for CSV exports.
    """

    timetable_id: str = Field(
        ...,
        min_length=1,
        description="UUID from the generation step — used as the download filename.",
        examples=["a1b2c3d4-0000-0000-0000-000000000000"],
    )
    schedule: List[ScheduledSlot] = Field(
        ...,
        min_length=1,
        description="Complete schedule to export. Must not be empty.",
    )
    title: str = Field(
        default="Exam Timetable",
        max_length=120,
        description="Title shown in the PDF header. Ignored for CSV.",
        examples=["Final Semester Exam Timetable 2025"],
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "timetable_id": "a1b2c3d4-0000-0000-0000-000000000000",
                "title":        "Final Semester Exam Timetable",
                "schedule": [
                    {
                        "subject_id":    "CS101",
                        "subject_name":  "Data Structures",
                        "day":           1,
                        "slot":          1,
                        "slot_label":    "Day 1 – Morning",
                        "duration":      120,
                        "student_count": 35,
                        "color":         1,
                    }
                ],
            }
        }
    }


# ════════════════════════════════════════════════════════════════
# SHARED HELPERS
# ════════════════════════════════════════════════════════════════

def _short_id(timetable_id: str) -> str:
    """
    Return the first 8 characters of the timetable UUID.
    Used for log messages and download filenames.

    'a1b2c3d4-...' → 'a1b2c3d4'
    """
    return timetable_id.replace("-", "")[:8]


def _streaming_response(
    content: bytes,
    media_type: str,
    filename: str,
) -> StreamingResponse:
    """
    Wrap raw bytes in a StreamingResponse that triggers a browser
    'Save As' dialog via the Content-Disposition header.

    Parameters
    ----------
    content    : bytes   — file content to stream
    media_type : str     — MIME type (text/csv or application/pdf)
    filename   : str     — suggested download filename

    Returns
    -------
    StreamingResponse
    """
    return StreamingResponse(
        content=iter([content]),
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Length":      str(len(content)),
            # Allow the frontend to read Content-Disposition from JS
            "Access-Control-Expose-Headers": "Content-Disposition",
        },
    )


# ════════════════════════════════════════════════════════════════
# ENDPOINTS
# ════════════════════════════════════════════════════════════════

@router.post(
    "/csv",
    summary="Export Timetable as CSV",
    description=(
        "Accepts a generated schedule and streams back a **UTF-8 CSV file** "
        "ready for download.\n\n"
        "The file includes a BOM so it opens correctly in **Microsoft Excel** "
        "on Windows without encoding issues.\n\n"
        "The `Content-Disposition` header triggers the browser's "
        "'Save As' dialog automatically."
    ),
    response_class=StreamingResponse,
    responses={
        200: {
            "description": "CSV file streamed successfully.",
            "content": {"text/csv": {}},
        },
        422: {"description": "Schedule payload is empty or invalid."},
        500: {"description": "Unexpected error during CSV generation."},
    },
)
async def export_csv(payload: ExportPayload) -> StreamingResponse:
    """
    **POST /api/v1/export/csv**

    ### What you get
    A `.csv` file sorted by day → slot with columns:

    | Column | Description |
    |--------|-------------|
    | Day | Exam day number |
    | Slot | Slot number within the day |
    | Schedule | Human-readable label (e.g. 'Day 1 – Morning') |
    | Subject Code | subject_id |
    | Subject Name | Full subject name |
    | Duration (min) | Exam duration |
    | Students | Number of enrolled students |

    ### Usage
    Post the `schedule` array from the `/generate` response directly here.
    """
    short = _short_id(payload.timetable_id)
    logger.info(
        f"[{short}] CSV export requested — "
        f"{len(payload.schedule)} entry/entries."
    )

    try:
        csv_bytes = build_csv_bytes(payload.schedule)

    except ValueError as exc:
        # build_csv_bytes raises ValueError for empty schedules
        # (Pydantic min_length=1 should prevent this, but belt-and-suspenders)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        )

    except Exception as exc:
        logger.error(f"[{short}] CSV generation failed: {exc}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate CSV file. Please try again.",
        )

    filename = f"timetable_{short}.csv"
    logger.info(f"[{short}] CSV ready — {len(csv_bytes):,} bytes → '{filename}'")

    return _streaming_response(
        content    = csv_bytes,
        media_type = "text/csv",
        filename   = filename,
    )


@router.post(
    "/pdf",
    summary="Export Timetable as PDF",
    description=(
        "Accepts a generated schedule and streams back a **formatted PDF** "
        "document ready for download or printing.\n\n"
        "The PDF includes:\n"
        "- Branded header with the timetable title and generation timestamp\n"
        "- Summary statistics (total exams, days used, total enrollments)\n"
        "- Color-coded schedule table (Morning / Afternoon / Evening)\n"
        "- Slot colour legend\n"
        "- Page number footer\n\n"
        "The `Content-Disposition` header triggers the browser's "
        "'Save As' dialog automatically."
    ),
    response_class=StreamingResponse,
    responses={
        200: {
            "description": "PDF file streamed successfully.",
            "content": {"application/pdf": {}},
        },
        422: {"description": "Schedule payload is empty or invalid."},
        500: {"description": "Unexpected error during PDF generation."},
    },
)
async def export_pdf(payload: ExportPayload) -> StreamingResponse:
    """
    **POST /api/v1/export/pdf**

    ### What you get
    A landscape A4 PDF with:
    - ClashZero branded header + generation timestamp
    - Summary stats bar (exams, days, total enrollments)
    - Color-coded table sorted by day and slot
    - Slot colour legend (Morning / Afternoon / Evening)
    - Page number footer on every page

    ### Usage
    Post the `schedule` array from the `/generate` response directly here.
    Include a `title` string to customise the document header.
    """
    short = _short_id(payload.timetable_id)
    logger.info(
        f"[{short}] PDF export requested — "
        f"{len(payload.schedule)} entry/entries, "
        f"title='{payload.title}'."
    )

    try:
        pdf_bytes = build_pdf_bytes(
            schedule = payload.schedule,
            title    = payload.title,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        )

    except Exception as exc:
        logger.error(f"[{short}] PDF generation failed: {exc}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate PDF file. Please try again.",
        )

    filename = f"timetable_{short}.pdf"
    logger.info(f"[{short}] PDF ready — {len(pdf_bytes):,} bytes → '{filename}'")

    return _streaming_response(
        content    = pdf_bytes,
        media_type = "application/pdf",
        filename   = filename,
    )
