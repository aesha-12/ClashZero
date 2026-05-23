"""
╔══════════════════════════════════════════════════════════════╗
║         ClashZero — AI Exam Timetable Generator              ║
║         routes/generate.py · Timetable Generation Endpoint   ║
║         Member 2: Engine Room (Backend & API)                ║
╚══════════════════════════════════════════════════════════════╝

Responsibilities:
  - Accept validated TimetableRequest from the React frontend
  - Bridge the API layer to the Graph Coloring algorithm module
  - Return a fully structured TimetableResponse
  - Provide a deterministic stub when the algorithm module is not
    yet connected (enables parallel frontend development)

Flow:
  POST /api/v1/generate/
      │
      ├─ Pydantic validates request body  (models.py)
      │
      ├─ _run_algorithm()
      │       ├─ Algorithm available?  → GraphColoringScheduler.generate()
      │       └─ Not available?        → _stub_schedule() (mock)
      │
      └─ Map raw output → TimetableResponse → return to client
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, status

from api.models import (
    ScheduledSlot,
    TimetableRequest,
    TimetableResponse,
    TimetableStatus,
)

# ---------------------------------------------------------------------------
# Algorithm module integration
# Imported with a graceful fallback so the API layer can be built,
# tested, and demoed independently of Member 1's algorithm module.
# Once the algorithm lands, this import resolves and the stub is bypassed.
# ---------------------------------------------------------------------------
try:
    from algorithm.graph_coloring import GraphColoringScheduler  # type: ignore
    ALGORITHM_AVAILABLE = True
    _alg_status = "GraphColoringScheduler loaded ✓"
except ImportError:
    ALGORITHM_AVAILABLE = False
    _alg_status = "Algorithm module not found — stub mode active"

logger = logging.getLogger("clashzero.generate")
logger.info(_alg_status)

router = APIRouter()


# ════════════════════════════════════════════════════════════════
# INTERNAL HELPERS
# ════════════════════════════════════════════════════════════════

# Slot number → human-readable label mapping
_SLOT_LABELS: Dict[int, str] = {
    1: "Morning",
    2: "Afternoon",
    3: "Evening",
    4: "Late Evening",
    5: "Night",
    6: "Late Night",
}


def _slot_label(day: int, slot: int) -> str:
    """Build a consistent slot label string, e.g. 'Day 2 – Afternoon'."""
    label = _SLOT_LABELS.get(slot, f"Slot {slot}")
    return f"Day {day} – {label}"


def _stub_schedule(request: TimetableRequest) -> Dict[str, Any]:
    """
    Deterministic round-robin stub schedule.

    Maps subjects sequentially across days and slots so the
    frontend integration can be developed and tested end-to-end
    without waiting for the real algorithm.

    Remove this once Member 1's GraphColoringScheduler is connected.

    Parameters
    ----------
    request : TimetableRequest
        The validated generation request.

    Returns
    -------
    dict
        Raw schedule dict matching the shape expected by _map_response().
    """
    schedule = []

    for idx, subject in enumerate(request.subjects):
        day  = (idx // request.slots_per_day) + 1
        slot = (idx %  request.slots_per_day) + 1

        schedule.append({
            "subject_id":    subject.subject_id,
            "subject_name":  subject.subject_name,
            "day":           day,
            "slot":          slot,
            "slot_label":    _slot_label(day, slot),
            "duration":      subject.duration,
            "student_count": len(subject.students),
            "color":         slot,   # colour = slot number in stub
        })

    days_used = max(e["day"] for e in schedule) if schedule else 0

    return {
        "schedule":           schedule,
        "total_days_used":    days_used,
        "conflicts_detected": 0,
        "algorithm_meta": {
            "mode":       "stub",
            "note":       "Real algorithm not connected yet.",
            "iterations": 0,
            "time_ms":    0,
        },
    }


def _run_algorithm(request: TimetableRequest) -> Dict[str, Any]:
    """
    Bridge between the FastAPI layer and the graph-coloring engine.

    Tries the real GraphColoringScheduler first; falls back to the
    deterministic stub if the module is unavailable.

    Parameters
    ----------
    request : TimetableRequest
        Fully validated generation request.

    Returns
    -------
    dict
        Raw algorithm output containing 'schedule', 'total_days_used',
        'conflicts_detected', and 'algorithm_meta'.

    Raises
    ------
    HTTPException 422
        When the algorithm rejects a scheduling constraint
        (e.g. too many subjects for the given days/slots).
    HTTPException 409
        When the algorithm exhausts its backtracking budget without
        finding a conflict-free assignment.
    HTTPException 503
        For unexpected infrastructure-level failures inside the engine.
    """
    if not ALGORITHM_AVAILABLE:
        logger.warning(
            "Algorithm module unavailable — falling back to stub schedule. "
            "Connect algorithm/graph_coloring.py to enable real scheduling."
        )
        return _stub_schedule(request)

    try:
        scheduler = GraphColoringScheduler(
            max_days=request.max_days,
            slots_per_day=request.slots_per_day,
        )
        subjects_data = [s.model_dump() for s in request.subjects]
        raw = scheduler.generate(subjects_data)

        # Ensure slot_label is always present even if algorithm omits it
        for entry in raw.get("schedule", []):
            if "slot_label" not in entry:
                entry["slot_label"] = _slot_label(entry["day"], entry["slot"])

        return raw

    except ValueError as exc:
        # Algorithm received logically invalid constraints
        logger.warning(f"Algorithm constraint error: {exc}")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Scheduling constraint error: {exc}",
        )

    except RuntimeError as exc:
        # Algorithm exhausted backtracking — no valid colouring found
        logger.error(f"Algorithm could not find valid schedule: {exc}")
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "The algorithm could not produce a conflict-free timetable "
                f"within the given constraints: {exc}"
            ),
        )

    except Exception as exc:
        # Unexpected engine failure — log fully, hide details from client
        logger.error(f"Unexpected algorithm failure: {exc}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The scheduling engine encountered an unexpected error.",
        )


def _map_response(
    timetable_id: str,
    request: TimetableRequest,
    raw: Dict[str, Any],
) -> TimetableResponse:
    """
    Convert the raw algorithm output dict into a typed TimetableResponse.

    Keeps the route handler clean — all mapping logic lives here.

    Parameters
    ----------
    timetable_id : str
        UUID assigned to this generation run.
    request : TimetableRequest
        Original validated request (for metadata like total_subjects).
    raw : dict
        Output from _run_algorithm().

    Returns
    -------
    TimetableResponse
    """
    schedule = [ScheduledSlot(**entry) for entry in raw["schedule"]]

    return TimetableResponse(
        timetable_id=timetable_id,
        status=TimetableStatus.GENERATED,
        message=(
            f"Timetable generated successfully. "
            f"{len(schedule)} exam(s) scheduled across "
            f"{raw.get('total_days_used', 0)} day(s)."
        ),
        total_subjects=len(request.subjects),
        total_days_used=raw.get("total_days_used", 0),
        schedule=schedule,
        conflicts_detected=raw.get("conflicts_detected", 0),
        algorithm_meta=raw.get("algorithm_meta", {}),
    )


# ════════════════════════════════════════════════════════════════
# ENDPOINT
# ════════════════════════════════════════════════════════════════

@router.post(
    "/",
    response_model=TimetableResponse,
    status_code=status.HTTP_200_OK,
    summary="Generate Exam Timetable",
    description=(
        "Accepts a list of subjects with student enrollment data and produces "
        "a **conflict-free exam timetable** using the Graph Coloring + "
        "Backtracking algorithm.\n\n"
        "Two subjects conflict when they share at least one student — "
        "conflicting subjects are assigned different time slots.\n\n"
        "The returned `timetable_id` can be used with the `/export` endpoints "
        "to download the result as CSV or PDF."
    ),
    responses={
        200: {"description": "Timetable generated successfully."},
        409: {"description": "No conflict-free schedule found within constraints."},
        422: {"description": "Invalid input or unsatisfiable scheduling constraint."},
        503: {"description": "Scheduling engine unavailable."},
    },
)
async def generate_timetable(request: TimetableRequest) -> TimetableResponse:
    """
    **POST /api/v1/generate/**

    ### Workflow
    1. Pydantic validates the request body against `TimetableRequest`.
    2. Subjects are forwarded to the Graph Coloring engine.
    3. The raw result is mapped to a structured `TimetableResponse`.
    4. A unique `timetable_id` (UUID) is attached for export calls.

    ### Algorithm Connection
    If `algorithm/graph_coloring.py` is present, the real scheduler runs.
    Otherwise a deterministic stub is used (safe for frontend development).
    """
    timetable_id = str(uuid.uuid4())

    logger.info(
        f"[{timetable_id[:8]}] Generation request received — "
        f"{len(request.subjects)} subject(s), "
        f"max_days={request.max_days}, "
        f"slots_per_day={request.slots_per_day}"
    )

    # Run algorithm (or stub)
    raw = _run_algorithm(request)

    # Map to typed response
    response = _map_response(timetable_id, request, raw)

    logger.info(
        f"[{timetable_id[:8]}] Done — "
        f"{len(response.schedule)} slot(s) across "
        f"{response.total_days_used} day(s), "
        f"{response.conflicts_detected} conflict(s) | "
        f"mode={response.algorithm_meta.get('mode', 'real')}"
    )

    return response
