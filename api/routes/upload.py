"""
╔══════════════════════════════════════════════════════════════╗
║         ClashZero — AI Exam Timetable Generator              ║
║         routes/upload.py · File Upload Endpoint              ║
║         Member 2: Engine Room (Backend & API)                ║
╚══════════════════════════════════════════════════════════════╝

Responsibilities:
  - Accept CSV or JSON file uploads from the React frontend
  - Enforce file size and type guards before parsing
  - Parse and validate each row/object into SubjectInput models
  - Return parsed subjects + any non-fatal warnings for UI preview

Supported formats:
  ┌─────────┬──────────────────────────────────────────────┐
  │  CSV    │ Columns: subject_id, subject_name, students, │
  │         │ preferred_slot, duration                     │
  │         │ students cell → semicolon or comma separated │
  ├─────────┼──────────────────────────────────────────────┤
  │  JSON   │ Single object OR array of SubjectInput objs  │
  └─────────┴──────────────────────────────────────────────┘

Flow:
  POST /api/v1/upload/subjects
        │
        ├─ Size guard   (max 5 MB)
        ├─ Type guard   (CSV or JSON only)
        │
        ├─ _parse_csv()   OR   _parse_json()
        │       ├─ Valid rows   → SubjectInput list
        │       └─ Bad rows     → warnings list (non-fatal)
        │
        └─ UploadResponse → client preview before generation
"""

from __future__ import annotations

import csv
import io
import json
import logging
from typing import List, Tuple

from fastapi import APIRouter, File, HTTPException, UploadFile, status

from api.models import SubjectInput, UploadResponse

logger = logging.getLogger("clashzero.upload")
router = APIRouter()


# ════════════════════════════════════════════════════════════════
# CONSTANTS
# ════════════════════════════════════════════════════════════════

MAX_FILE_SIZE_BYTES = 5 * 1024 * 1024   # 5 MB hard limit

# Columns that MUST be present in a CSV upload (case-insensitive match)
REQUIRED_CSV_COLUMNS = {
    "subject_id",
    "subject_name",
    "students",
    "preferred_slot",
    "duration",
}

# MIME types we accept (browsers report these inconsistently,
# so we check file extension as the authoritative source)
ACCEPTED_EXTENSIONS = {"csv", "json"}


# ════════════════════════════════════════════════════════════════
# PARSERS
# ════════════════════════════════════════════════════════════════

def _parse_csv(content: bytes) -> Tuple[List[SubjectInput], List[str]]:
    """
    Parse a UTF-8 CSV file into validated SubjectInput objects.

    CSV contract:
      - First row must be a header row (column names, case-insensitive)
      - Required columns: subject_id, subject_name, students,
                          preferred_slot, duration
      - `students` cell: semicolon-separated IDs  →  "S001;S002;S003"
        (comma-separated also accepted as fallback)
      - Extra columns are silently ignored

    Strategy for bad rows:
      - Do NOT abort the entire upload on a single bad row.
      - Add a human-readable warning and continue.
      - Only raise HTTP 422 if ZERO valid subjects are found.

    Parameters
    ----------
    content : bytes
        Raw bytes of the uploaded file.

    Returns
    -------
    subjects : List[SubjectInput]
        Successfully parsed and validated subjects.
    warnings : List[str]
        Non-fatal issues (skipped rows, missing optional fields, etc.)

    Raises
    ------
    HTTPException 400
        If the file cannot be decoded as UTF-8.
    HTTPException 422
        If required CSV columns are missing entirely.
    """
    # ── Decode ──────────────────────────────────────────────────
    try:
        # utf-8-sig strips the BOM that Excel adds when saving CSV
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "CSV file must be UTF-8 encoded. "
                "If exported from Excel, use 'Save As → CSV UTF-8'."
            ),
        )

    # ── Header check ────────────────────────────────────────────
    reader = csv.DictReader(io.StringIO(text))

    if not reader.fieldnames:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="CSV file appears to be empty or has no header row.",
        )

    # Normalise headers to lowercase for case-insensitive matching
    normalised_headers = {h.strip().lower() for h in reader.fieldnames}
    missing_cols = REQUIRED_CSV_COLUMNS - normalised_headers

    if missing_cols:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"CSV is missing required column(s): {sorted(missing_cols)}. "
                f"Found: {sorted(normalised_headers)}"
            ),
        )

    # ── Row-by-row parsing ──────────────────────────────────────
    subjects: List[SubjectInput] = []
    warnings: List[str] = []

    for row_num, raw_row in enumerate(reader, start=2):  # start=2 (row 1 = header)

        # Normalise all keys and strip whitespace from values
        row = {
            k.strip().lower(): (v or "").strip()
            for k, v in raw_row.items()
            if k  # skip None keys that DictReader may inject
        }

        try:
            # Parse students cell: prefer semicolons, fall back to commas
            raw_students = row.get("students", "")
            delimiter    = ";" if ";" in raw_students else ","
            student_list = [s.strip() for s in raw_students.split(delimiter) if s.strip()]

            subject = SubjectInput(
                subject_id    = row["subject_id"],
                subject_name  = row["subject_name"],
                students      = student_list,
                preferred_slot= row.get("preferred_slot") or "Any",
                duration      = int(row["duration"]),
            )
            subjects.append(subject)

        except (ValueError, KeyError, Exception) as exc:
            warning_msg = f"Row {row_num} skipped — {exc}"
            warnings.append(warning_msg)
            logger.warning(f"CSV parse issue: {warning_msg}")

    return subjects, warnings


def _parse_json(content: bytes) -> Tuple[List[SubjectInput], List[str]]:
    """
    Parse a JSON file into validated SubjectInput objects.

    JSON contract:
      - File must be valid JSON (UTF-8)
      - Accepted shapes:
          • Single object  → { "subject_id": "CS101", ... }
          • Array of objects → [ { ... }, { ... } ]
      - Each object is validated against the SubjectInput schema

    Strategy for bad items:
      - Same as CSV: skip bad items, accumulate warnings, continue.

    Parameters
    ----------
    content : bytes
        Raw bytes of the uploaded file.

    Returns
    -------
    subjects : List[SubjectInput]
    warnings : List[str]

    Raises
    ------
    HTTPException 400
        If the content is not valid JSON.
    HTTPException 422
        If the top-level JSON structure is neither an object nor array.
    """
    # ── Decode & parse ───────────────────────────────────────────
    try:
        data = json.loads(content.decode("utf-8"))
    except UnicodeDecodeError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="JSON file must be UTF-8 encoded.",
        )
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid JSON — {exc.msg} at line {exc.lineno}, col {exc.colno}.",
        )

    # ── Normalise to list ────────────────────────────────────────
    if isinstance(data, dict):
        data = [data]   # Wrap single object → list of one

    if not isinstance(data, list):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "JSON must be a subject object or an array of subject objects. "
                f"Got top-level type: {type(data).__name__}."
            ),
        )

    # ── Item-by-item validation ──────────────────────────────────
    subjects: List[SubjectInput] = []
    warnings: List[str] = []

    for idx, item in enumerate(data, start=1):
        try:
            if not isinstance(item, dict):
                raise TypeError(f"Expected an object, got {type(item).__name__}.")
            subjects.append(SubjectInput(**item))

        except (ValueError, TypeError, Exception) as exc:
            warning_msg = f"Item {idx} skipped — {exc}"
            warnings.append(warning_msg)
            logger.warning(f"JSON parse issue: {warning_msg}")

    return subjects, warnings


# ════════════════════════════════════════════════════════════════
# HELPERS
# ════════════════════════════════════════════════════════════════

def _extract_extension(filename: str) -> str:
    """
    Return the lowercase file extension without the leading dot.
    Returns an empty string if no extension is present.
    """
    if "." not in filename:
        return ""
    return filename.rsplit(".", 1)[-1].lower().strip()


# ════════════════════════════════════════════════════════════════
# ENDPOINT
# ════════════════════════════════════════════════════════════════

@router.post(
    "/subjects",
    response_model=UploadResponse,
    status_code=status.HTTP_200_OK,
    summary="Upload Subject Data File",
    description=(
        "Upload a **CSV** or **JSON** file containing subject and "
        "student enrollment data.\n\n"
        "The parsed subjects are returned for a **confirmation preview** "
        "in the UI before timetable generation is triggered.\n\n"
        "### CSV Format\n"
        "```\n"
        "subject_id,subject_name,students,preferred_slot,duration\n"
        "CS101,Data Structures,S001;S002;S003,Morning,120\n"
        "MATH201,Linear Algebra,S002;S004,Afternoon,90\n"
        "```\n\n"
        "### JSON Format\n"
        "```json\n"
        '[\n  { "subject_id": "CS101", "subject_name": "Data Structures",\n'
        '    "students": ["S001","S002"], "preferred_slot": "Morning", "duration": 120 }\n]\n'
        "```"
    ),
    responses={
        200: {"description": "File parsed successfully. Subjects returned for preview."},
        400: {"description": "Unsupported file type or encoding error."},
        413: {"description": "File exceeds the 5 MB size limit."},
        422: {"description": "File structure is invalid or no valid subjects found."},
    },
)
async def upload_subjects(
    file: UploadFile = File(
        ...,
        description="A .csv or .json file containing subject data.",
    ),
) -> UploadResponse:
    """
    **POST /api/v1/upload/subjects**

    ### Processing steps
    1. Read file bytes and enforce the 5 MB size limit.
    2. Detect format from file extension (.csv / .json).
    3. Parse and validate each row/item into a `SubjectInput`.
    4. Bad rows are skipped and reported as warnings — not errors.
    5. Return all valid subjects + warnings for frontend preview.

    ### After uploading
    Pass the returned `subjects` array directly into
    `POST /api/v1/generate/` to trigger timetable generation.
    """
    # ── Read file ────────────────────────────────────────────────
    file_bytes = await file.read()
    filename   = file.filename or "upload"
    file_size  = len(file_bytes)

    # ── Size guard ───────────────────────────────────────────────
    if file_size > MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=(
                f"File '{filename}' is {file_size:,} bytes — "
                f"exceeds the 5 MB limit ({MAX_FILE_SIZE_BYTES:,} bytes)."
            ),
        )

    logger.info(
        f"Upload received: '{filename}' "
        f"({file_size:,} bytes, content-type='{file.content_type}')"
    )

    # ── Type guard (extension is authoritative over MIME type) ───
    extension = _extract_extension(filename)

    if extension not in ACCEPTED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Unsupported file type '.{extension or 'unknown'}'. "
                "Please upload a .csv or .json file."
            ),
        )

    # ── Parse ────────────────────────────────────────────────────
    if extension == "csv":
        subjects, warnings = _parse_csv(file_bytes)
    else:
        subjects, warnings = _parse_json(file_bytes)

    # ── Require at least one valid subject ───────────────────────
    if not subjects:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"No valid subjects could be parsed from '{filename}'. "
                f"Encountered {len(warnings)} error(s): {warnings[:3]}"
            ),
        )

    logger.info(
        f"Parsed {len(subjects)} valid subject(s) from '{filename}' "
        f"with {len(warnings)} warning(s)."
    )

    return UploadResponse(
        filename        = filename,
        subjects_parsed = len(subjects),
        subjects        = subjects,
        warnings        = warnings,
    )
