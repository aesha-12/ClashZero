"""
╔══════════════════════════════════════════════════════════════╗
║         ClashZero — AI Exam Timetable Generator              ║
║         models.py · Pydantic Schemas & Data Contracts        ║
║         Member 2: Engine Room (Backend & API)                ║
╚══════════════════════════════════════════════════════════════╝

All request bodies, response shapes, and domain types are defined
here so every other module imports from a single source of truth.

Schema hierarchy:
  Enums
    └─ SlotPreference, ExportFormat, TimetableStatus

  Request Models
    └─ SubjectInput          ← one exam subject
    └─ TimetableRequest      ← list of SubjectInput + config
    └─ ExportPayload         ← schedule + format for export routes

  Response Models
    └─ ScheduledSlot         ← one entry in the final timetable
    └─ TimetableResponse     ← full generation result
    └─ UploadResponse        ← parsed subjects from file upload
    └─ ErrorResponse         ← standard error envelope
"""

from __future__ import annotations

import re
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


# ════════════════════════════════════════════════════════════════
# ENUMS
# ════════════════════════════════════════════════════════════════

class SlotPreference(str, Enum):
    """
    Preferred time-of-day band for scheduling an exam.
    Passed to the graph-coloring engine as a soft constraint.
    """
    MORNING   = "Morning"
    AFTERNOON = "Afternoon"
    EVENING   = "Evening"
    ANY       = "Any"          # No preference — scheduler decides


class ExportFormat(str, Enum):
    """Supported timetable export formats."""
    CSV = "csv"
    PDF = "pdf"


class TimetableStatus(str, Enum):
    """Lifecycle state of a timetable generation request."""
    PENDING   = "pending"
    GENERATED = "generated"
    FAILED    = "failed"


# ════════════════════════════════════════════════════════════════
# REQUEST MODELS
# ════════════════════════════════════════════════════════════════

class SubjectInput(BaseModel):
    """
    Represents a single exam subject submitted for scheduling.

    This is the core unit the graph-coloring algorithm operates on.
    Two subjects that share at least one student become connected nodes
    in the conflict graph — they cannot share a time slot.

    Validation rules enforced:
    - subject_id  : alphanumeric + hyphens/underscores only, auto-uppercased
    - students    : deduplicated, non-empty, valid ID format each
    - duration    : 30–300 minutes
    - subject_name: stripped of leading/trailing whitespace
    """

    subject_id: str = Field(
        ...,
        min_length=2,
        max_length=20,
        description="Unique subject code, e.g. 'CS101'. Auto-uppercased.",
        examples=["CS101"],
    )
    subject_name: str = Field(
        ...,
        min_length=2,
        max_length=100,
        description="Human-readable subject name.",
        examples=["Data Structures"],
    )
    students: List[str] = Field(
        ...,
        min_length=1,
        description=(
            "List of student IDs enrolled in this subject. "
            "Shared students between two subjects create a scheduling conflict."
        ),
        examples=[["S001", "S002", "S003"]],
    )
    preferred_slot: SlotPreference = Field(
        default=SlotPreference.ANY,
        description="Preferred time-of-day band. Used as a soft constraint.",
    )
    duration: int = Field(
        ...,
        ge=30,
        le=300,
        description="Exam duration in minutes. Must be between 30 and 300.",
        examples=[120],
    )
    room_capacity: Optional[int] = Field(
        default=None,
        ge=1,
        description="Minimum room seating capacity needed (optional).",
    )

    # ----------------------------------------------------------------
    # Field Validators
    # ----------------------------------------------------------------

    @field_validator("subject_id")
    @classmethod
    def validate_subject_id(cls, v: str) -> str:
        """
        Enforce safe, predictable subject ID format.
        Only letters, digits, hyphens, and underscores are allowed.
        IDs are stored in UPPERCASE for consistent graph-node keying.
        """
        v = v.strip()
        if not re.match(r"^[A-Za-z0-9_\-]+$", v):
            raise ValueError(
                f"subject_id '{v}' may only contain letters, digits, "
                "hyphens (-), or underscores (_)."
            )
        return v.upper()

    @field_validator("subject_name")
    @classmethod
    def sanitize_subject_name(cls, v: str) -> str:
        """Strip accidental whitespace from subject names."""
        return v.strip()

    @field_validator("students")
    @classmethod
    def validate_and_deduplicate_students(cls, v: List[str]) -> List[str]:
        """
        Validate each student ID and silently deduplicate.

        Rules:
        - No empty strings
        - Alphanumeric + hyphens/underscores only
        - Duplicates are removed (preserving first occurrence order)
        """
        seen: set = set()
        cleaned: List[str] = []

        for sid in v:
            sid = sid.strip()

            if not sid:
                raise ValueError("Student ID cannot be an empty string.")

            if not re.match(r"^[A-Za-z0-9_\-]+$", sid):
                raise ValueError(
                    f"Invalid student ID format: '{sid}'. "
                    "Only letters, digits, hyphens, and underscores are allowed."
                )

            if sid not in seen:
                seen.add(sid)
                cleaned.append(sid)

        return cleaned

    model_config = {
        "json_schema_extra": {
            "example": {
                "subject_id":     "CS101",
                "subject_name":   "Data Structures",
                "students":       ["S001", "S002", "S003"],
                "preferred_slot": "Morning",
                "duration":       120,
            }
        }
    }


class TimetableRequest(BaseModel):
    """
    Full timetable generation request sent by the React frontend.

    Contains the list of subjects to schedule plus algorithm
    configuration parameters (max days, slots per day).

    Cross-field validation:
    - No duplicate subject_id values across the list
    """

    subjects: List[SubjectInput] = Field(
        ...,
        min_length=1,
        description="One or more subjects to schedule. Must have unique subject_id values.",
    )
    max_days: int = Field(
        default=5,
        ge=1,
        le=30,
        description="Maximum number of exam days the scheduler may use.",
    )
    slots_per_day: int = Field(
        default=3,
        ge=1,
        le=6,
        description="Number of distinct time slots available per day.",
    )

    @model_validator(mode="after")
    def check_unique_subject_ids(self) -> TimetableRequest:
        """
        Reject requests that contain duplicate subject IDs.
        Duplicates would create ambiguous graph nodes and corrupt the schedule.
        """
        ids = [s.subject_id for s in self.subjects]
        duplicates = {sid for sid in ids if ids.count(sid) > 1}
        if duplicates:
            raise ValueError(
                f"Duplicate subject_id(s) found: {sorted(duplicates)}. "
                "Every subject in a single request must have a unique ID."
            )
        return self

    model_config = {
        "json_schema_extra": {
            "example": {
                "subjects": [
                    {
                        "subject_id":     "CS101",
                        "subject_name":   "Data Structures",
                        "students":       ["S001", "S002"],
                        "preferred_slot": "Morning",
                        "duration":       120,
                    },
                    {
                        "subject_id":     "MATH201",
                        "subject_name":   "Linear Algebra",
                        "students":       ["S002", "S003"],
                        "preferred_slot": "Afternoon",
                        "duration":       90,
                    },
                ],
                "max_days":      5,
                "slots_per_day": 3,
            }
        }
    }


# ════════════════════════════════════════════════════════════════
# RESPONSE MODELS
# ════════════════════════════════════════════════════════════════

class ScheduledSlot(BaseModel):
    """
    A single exam entry in the generated timetable.

    Produced by the graph-coloring engine and returned inside
    TimetableResponse. Also used as the payload body for export endpoints.

    `color` is the internal graph node colour (integer) assigned by the
    algorithm — it maps directly to a unique time slot.
    """

    subject_id:    str = Field(..., description="Subject code.")
    subject_name:  str = Field(..., description="Subject name.")
    day:           int = Field(..., ge=1, description="Exam day number (1-indexed).")
    slot:          int = Field(..., ge=1, description="Slot within the day (1-indexed).")
    slot_label:    str = Field(..., description="Human-readable label, e.g. 'Day 1 – Morning'.")
    duration:      int = Field(..., description="Exam duration in minutes.")
    student_count: int = Field(..., description="Number of students sitting this exam.")
    color:         int = Field(..., description="Graph coloring node colour (internal).")


class TimetableResponse(BaseModel):
    """
    Response returned to the frontend after successful timetable generation.

    Includes the full schedule, summary statistics, and algorithm
    diagnostics for transparency / debugging.
    """

    timetable_id:       str               = Field(..., description="UUID assigned to this timetable run.")
    status:             TimetableStatus   = Field(..., description="Generation lifecycle state.")
    message:            str               = Field(..., description="Human-readable outcome summary.")
    total_subjects:     int               = Field(..., description="Number of subjects scheduled.")
    total_days_used:    int               = Field(..., description="Actual days used by the schedule.")
    schedule:           List[ScheduledSlot]
    conflicts_detected: int               = Field(default=0, description="Remaining conflicts (0 = perfect).")
    algorithm_meta:     Dict[str, Any]    = Field(
        default_factory=dict,
        description="Diagnostics from the engine: iterations, time_ms, coloring strategy, etc.",
    )


class UploadResponse(BaseModel):
    """
    Response after a successful subject data file upload.

    Returns the parsed subjects so the frontend can display
    a confirmation preview before triggering generation.
    """

    filename:        str               = Field(..., description="Original uploaded filename.")
    subjects_parsed: int               = Field(..., description="Number of valid subjects extracted.")
    subjects:        List[SubjectInput] = Field(..., description="Parsed and validated subjects.")
    warnings:        List[str]         = Field(
        default_factory=list,
        description="Non-fatal parse issues (e.g. skipped rows with bad data).",
    )


class ErrorResponse(BaseModel):
    """
    Standard error envelope returned on 4xx / 5xx responses.

    Using a typed model here means the React frontend can rely on
    a consistent shape for all error handling.
    """

    detail: str            = Field(..., description="Human-readable error description.")
    field:  Optional[str]  = Field(default=None, description="Specific field that caused the error, if applicable.")
    code:   Optional[str]  = Field(default=None, description="Machine-readable error code for frontend logic.")
