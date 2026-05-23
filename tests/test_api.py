"""
╔══════════════════════════════════════════════════════════════╗
║         ClashZero — AI Exam Timetable Generator              ║
║         tests/test_api.py · Full API Test Suite              ║
║         Member 2: Engine Room (Backend & API)                ║
╚══════════════════════════════════════════════════════════════╝

Test coverage:
  ┌──────────────────────────┬────────────────────────────────┐
  │  Class                   │  What is tested                │
  ├──────────────────────────┼────────────────────────────────┤
  │  TestSystemEndpoints     │  /health, /                    │
  │  TestSubjectInputModel   │  Pydantic validation unit tests│
  │  TestGenerateEndpoint    │  POST /api/v1/generate/        │
  │  TestUploadEndpoint      │  POST /api/v1/upload/subjects  │
  │  TestExportCSV           │  POST /api/v1/export/csv       │
  │  TestExportPDF           │  POST /api/v1/export/pdf       │
  │  TestCSVExportUtil       │  utils/csv_export unit tests   │
  │  TestPDFExportUtil       │  utils/pdf_export unit tests   │
  └──────────────────────────┴────────────────────────────────┘

Run all tests:
    pytest tests/test_api.py -v

Run a specific class:
    pytest tests/test_api.py::TestGenerateEndpoint -v

Run with coverage:
    pytest tests/test_api.py --cov=api --cov-report=term-missing
"""

from __future__ import annotations

import io
import json

import pytest
from fastapi.testclient import TestClient

from api.main import app
from api.models import ScheduledSlot, SubjectInput
from api.utils.csv_export import build_csv_bytes
from api.utils.pdf_export import build_pdf_bytes

# ════════════════════════════════════════════════════════════════
# TEST CLIENT
# ════════════════════════════════════════════════════════════════

client = TestClient(app, raise_server_exceptions=False)


# ════════════════════════════════════════════════════════════════
# SHARED FIXTURES & FACTORIES
# ════════════════════════════════════════════════════════════════

def make_subject(
    subject_id:     str  = "CS101",
    subject_name:   str  = "Data Structures",
    students:       list = None,
    preferred_slot: str  = "Morning",
    duration:       int  = 120,
) -> dict:
    """
    Factory for a valid subject dict.
    Override any field to test edge cases without repeating boilerplate.
    """
    return {
        "subject_id":     subject_id,
        "subject_name":   subject_name,
        "students":       students or ["S001", "S002", "S003"],
        "preferred_slot": preferred_slot,
        "duration":       duration,
    }


def make_request(subjects: list = None, max_days: int = 5, slots_per_day: int = 3) -> dict:
    """Factory for a valid TimetableRequest dict."""
    return {
        "subjects":      subjects or [make_subject()],
        "max_days":      max_days,
        "slots_per_day": slots_per_day,
    }


def make_scheduled_slot(
    subject_id:    str = "CS101",
    subject_name:  str = "Data Structures",
    day:           int = 1,
    slot:          int = 1,
    slot_label:    str = "Day 1 – Morning",
    duration:      int = 120,
    student_count: int = 30,
    color:         int = 1,
) -> dict:
    """Factory for a valid ScheduledSlot dict (used in export tests)."""
    return {
        "subject_id":    subject_id,
        "subject_name":  subject_name,
        "day":           day,
        "slot":          slot,
        "slot_label":    slot_label,
        "duration":      duration,
        "student_count": student_count,
        "color":         color,
    }


def make_export_payload(schedule: list = None, title: str = "Test Timetable") -> dict:
    """Factory for a valid ExportPayload dict."""
    return {
        "timetable_id": "a1b2c3d4-0000-0000-0000-000000000000",
        "title":        title,
        "schedule":     schedule or [make_scheduled_slot()],
    }


# ════════════════════════════════════════════════════════════════
# 1. SYSTEM ENDPOINTS
# ════════════════════════════════════════════════════════════════

class TestSystemEndpoints:
    """Tests for utility routes: /health and /"""

    def test_health_returns_200(self):
        """Health check must respond 200 with status=ok."""
        r = client.get("/health")
        assert r.status_code == 200

    def test_health_body(self):
        """Health response must include status, service, and version keys."""
        body = client.get("/health").json()
        assert body["status"]  == "ok"
        assert body["service"] == "ClashZero API"
        assert "version" in body

    def test_root_returns_200(self):
        r = client.get("/")
        assert r.status_code == 200

    def test_root_contains_docs_link(self):
        body = client.get("/").json()
        assert "docs" in body or "interactive_docs" in body

    def test_root_contains_endpoint_map(self):
        """Root should expose endpoint discovery map."""
        body = client.get("/").json()
        assert "endpoints" in body


# ════════════════════════════════════════════════════════════════
# 2. PYDANTIC MODEL UNIT TESTS
# ════════════════════════════════════════════════════════════════

class TestSubjectInputModel:
    """Unit tests for SubjectInput Pydantic model validators."""

    def test_valid_subject_parses_correctly(self):
        s = SubjectInput(**make_subject())
        assert s.subject_id   == "CS101"
        assert s.subject_name == "Data Structures"
        assert s.duration     == 120

    def test_subject_id_uppercased(self):
        """subject_id must be auto-uppercased regardless of input case."""
        s = SubjectInput(**make_subject(subject_id="cs101"))
        assert s.subject_id == "CS101"

    def test_subject_id_rejects_spaces(self):
        with pytest.raises(Exception):
            SubjectInput(**make_subject(subject_id="CS 101"))

    def test_subject_id_rejects_special_chars(self):
        with pytest.raises(Exception):
            SubjectInput(**make_subject(subject_id="CS@101!"))

    def test_subject_id_allows_hyphens_and_underscores(self):
        s = SubjectInput(**make_subject(subject_id="CS-101_A"))
        assert s.subject_id == "CS-101_A"

    def test_students_deduplicated(self):
        """Duplicate student IDs must be silently removed."""
        s = SubjectInput(**make_subject(students=["S001", "S001", "S002"]))
        assert s.students == ["S001", "S002"]

    def test_empty_students_rejected(self):
        with pytest.raises(Exception):
            SubjectInput(**make_subject(students=[]))

    def test_invalid_student_id_rejected(self):
        with pytest.raises(Exception):
            SubjectInput(**make_subject(students=["S 001"]))  # space in ID

    def test_duration_below_minimum_rejected(self):
        with pytest.raises(Exception):
            SubjectInput(**make_subject(duration=10))   # min is 30

    def test_duration_above_maximum_rejected(self):
        with pytest.raises(Exception):
            SubjectInput(**make_subject(duration=999))  # max is 300

    def test_subject_name_stripped(self):
        """Leading/trailing whitespace must be stripped from subject_name."""
        s = SubjectInput(**make_subject(subject_name="  Data Structures  "))
        assert s.subject_name == "Data Structures"

    def test_preferred_slot_defaults_to_any(self):
        data = make_subject()
        data.pop("preferred_slot")
        s = SubjectInput(**data)
        assert s.preferred_slot.value == "Any"

    def test_invalid_preferred_slot_rejected(self):
        with pytest.raises(Exception):
            SubjectInput(**make_subject(preferred_slot="Midnight"))


# ════════════════════════════════════════════════════════════════
# 3. GENERATE ENDPOINT
# ════════════════════════════════════════════════════════════════

class TestGenerateEndpoint:
    """Integration tests for POST /api/v1/generate/"""

    def test_single_subject_returns_200(self):
        r = client.post("/api/v1/generate/", json=make_request())
        assert r.status_code == 200

    def test_multiple_subjects_scheduled(self):
        subjects = [
            make_subject("CS101", "Data Structures",   ["S001", "S002"]),
            make_subject("MA201", "Linear Algebra",    ["S002", "S003"]),
            make_subject("PH301", "Quantum Physics",   ["S004", "S005"]),
        ]
        r = client.post("/api/v1/generate/", json=make_request(subjects=subjects))
        assert r.status_code == 200
        body = r.json()
        assert len(body["schedule"]) == 3

    def test_response_contains_timetable_id(self):
        """timetable_id must be a valid UUID (36 chars with hyphens)."""
        r    = client.post("/api/v1/generate/", json=make_request())
        body = r.json()
        assert "timetable_id" in body
        assert len(body["timetable_id"]) == 36
        assert body["timetable_id"].count("-") == 4

    def test_response_status_is_generated(self):
        r = client.post("/api/v1/generate/", json=make_request())
        assert r.json()["status"] == "generated"

    def test_total_subjects_matches_input(self):
        subjects = [
            make_subject("CS101", students=["S001"]),
            make_subject("CS102", students=["S002"]),
        ]
        r = client.post("/api/v1/generate/", json=make_request(subjects=subjects))
        assert r.json()["total_subjects"] == 2

    def test_schedule_entries_have_required_fields(self):
        """Every ScheduledSlot in the response must have all required fields."""
        r     = client.post("/api/v1/generate/", json=make_request())
        entry = r.json()["schedule"][0]
        for field in ["subject_id", "subject_name", "day", "slot",
                      "slot_label", "duration", "student_count", "color"]:
            assert field in entry, f"Missing field: {field}"

    def test_empty_subjects_list_rejected(self):
        r = client.post("/api/v1/generate/", json=make_request(subjects=[]))
        assert r.status_code == 422

    def test_duplicate_subject_ids_rejected(self):
        """Two subjects with the same subject_id must fail validation."""
        subjects = [
            make_subject("CS101"),
            make_subject("CS101"),  # duplicate
        ]
        r = client.post("/api/v1/generate/", json=make_request(subjects=subjects))
        assert r.status_code == 422

    def test_invalid_duration_rejected(self):
        r = client.post(
            "/api/v1/generate/",
            json=make_request(subjects=[make_subject(duration=5)]),
        )
        assert r.status_code == 422

    def test_max_days_out_of_range_rejected(self):
        r = client.post("/api/v1/generate/", json=make_request(max_days=0))
        assert r.status_code == 422

    def test_slots_per_day_out_of_range_rejected(self):
        r = client.post("/api/v1/generate/", json=make_request(slots_per_day=10))
        assert r.status_code == 422

    def test_algorithm_meta_present_in_response(self):
        r = client.post("/api/v1/generate/", json=make_request())
        assert "algorithm_meta" in r.json()

    def test_response_has_process_time_header(self):
        """Every response must carry the X-Process-Time timing header."""
        r = client.post("/api/v1/generate/", json=make_request())
        assert "x-process-time" in r.headers

    def test_subject_id_case_normalised(self):
        """Lowercase subject_id in input must be uppercased in the response."""
        subjects = [make_subject(subject_id="cs101")]
        r        = client.post("/api/v1/generate/", json=make_request(subjects=subjects))
        entry    = r.json()["schedule"][0]
        assert entry["subject_id"] == "CS101"

    def test_conflicting_students_get_different_slots(self):
        """
        Subjects sharing a student must be assigned different (day, slot) pairs.
        CS101 and MA201 share S002 — they must not collide.
        """
        subjects = [
            make_subject("CS101", students=["S001", "S002"]),
            make_subject("MA201", students=["S002", "S003"]),
        ]
        r        = client.post("/api/v1/generate/", json=make_request(subjects=subjects))
        schedule = r.json()["schedule"]
        slots    = [(e["day"], e["slot"]) for e in schedule]
        assert len(slots) == len(set(slots)), (
            "Conflicting subjects were assigned the same (day, slot)."
        )


# ════════════════════════════════════════════════════════════════
# 4. UPLOAD ENDPOINT
# ════════════════════════════════════════════════════════════════

class TestUploadEndpoint:
    """Integration tests for POST /api/v1/upload/subjects"""

    # ── JSON uploads ──────────────────────────────────────────

    def test_upload_single_json_object(self):
        """A single JSON object (not wrapped in array) must be accepted."""
        data = json.dumps(make_subject()).encode()
        r    = client.post(
            "/api/v1/upload/subjects",
            files={"file": ("subject.json", io.BytesIO(data), "application/json")},
        )
        assert r.status_code == 200
        assert r.json()["subjects_parsed"] == 1

    def test_upload_json_array(self):
        data = json.dumps([make_subject("CS101"), make_subject("MA201")]).encode()
        r    = client.post(
            "/api/v1/upload/subjects",
            files={"file": ("subjects.json", io.BytesIO(data), "application/json")},
        )
        assert r.status_code == 200
        assert r.json()["subjects_parsed"] == 2

    def test_upload_json_invalid_syntax(self):
        r = client.post(
            "/api/v1/upload/subjects",
            files={"file": ("bad.json", io.BytesIO(b"{ not valid json }"), "application/json")},
        )
        assert r.status_code == 400

    def test_upload_json_wrong_top_level_type(self):
        """A JSON number at the top level must be rejected."""
        data = b"42"
        r    = client.post(
            "/api/v1/upload/subjects",
            files={"file": ("num.json", io.BytesIO(data), "application/json")},
        )
        assert r.status_code == 422

    # ── CSV uploads ───────────────────────────────────────────

    def _make_csv(self, rows: list[str]) -> bytes:
        """Helper: build a CSV file with standard header + given data rows."""
        header = "subject_id,subject_name,students,preferred_slot,duration\n"
        return (header + "\n".join(rows)).encode("utf-8")

    def test_upload_valid_csv(self):
        csv_bytes = self._make_csv([
            "EE301,Circuit Theory,S010;S011;S012,Morning,90",
            "ME401,Thermodynamics,S013;S014,Afternoon,120",
        ])
        r = client.post(
            "/api/v1/upload/subjects",
            files={"file": ("data.csv", io.BytesIO(csv_bytes), "text/csv")},
        )
        assert r.status_code == 200
        assert r.json()["subjects_parsed"] == 2

    def test_upload_csv_semicolon_students(self):
        """Students separated by semicolons must parse correctly."""
        csv_bytes = self._make_csv(["CS101,Data Structures,S001;S002;S003,Morning,120"])
        r = client.post(
            "/api/v1/upload/subjects",
            files={"file": ("data.csv", io.BytesIO(csv_bytes), "text/csv")},
        )
        body = r.json()
        assert body["subjects_parsed"] == 1
        assert len(body["subjects"][0]["students"]) == 3

    def test_upload_csv_comma_students(self):
        """Students separated by commas (no semicolons) must also parse."""
        csv_bytes = self._make_csv(["CS101,Data Structures,\"S001,S002,S003\",Morning,120"])
        r = client.post(
            "/api/v1/upload/subjects",
            files={"file": ("data.csv", io.BytesIO(csv_bytes), "text/csv")},
        )
        assert r.status_code == 200

    def test_upload_csv_missing_required_column(self):
        """CSV without a required column must return 422."""
        bad_csv = b"subject_id,subject_name\nCS101,Data Structures\n"
        r = client.post(
            "/api/v1/upload/subjects",
            files={"file": ("bad.csv", io.BytesIO(bad_csv), "text/csv")},
        )
        assert r.status_code == 422

    def test_upload_csv_bad_rows_produce_warnings(self):
        """
        A file with one good row and one bad row must:
        - Return 200 (not abort)
        - Parse the good row
        - Include a warning for the bad row
        """
        csv_bytes = self._make_csv([
            "CS101,Data Structures,S001;S002,Morning,120",  # good
            "BAD,,,,notanumber",                             # bad duration
        ])
        r    = client.post(
            "/api/v1/upload/subjects",
            files={"file": ("mixed.csv", io.BytesIO(csv_bytes), "text/csv")},
        )
        body = r.json()
        assert r.status_code == 200
        assert body["subjects_parsed"] == 1
        assert len(body["warnings"]) >= 1

    def test_upload_csv_case_insensitive_headers(self):
        """CSV headers in any case must be accepted."""
        csv_bytes = b"SUBJECT_ID,Subject_Name,Students,Preferred_Slot,Duration\nCS101,DS,S001,Morning,90\n"
        r = client.post(
            "/api/v1/upload/subjects",
            files={"file": ("upper.csv", io.BytesIO(csv_bytes), "text/csv")},
        )
        assert r.status_code == 200

    # ── Guards ────────────────────────────────────────────────

    def test_upload_unsupported_extension_rejected(self):
        r = client.post(
            "/api/v1/upload/subjects",
            files={"file": ("data.xlsx", io.BytesIO(b"binary"), "application/octet-stream")},
        )
        assert r.status_code == 400

    def test_upload_empty_file_rejected(self):
        r = client.post(
            "/api/v1/upload/subjects",
            files={"file": ("empty.json", io.BytesIO(b"[]"), "application/json")},
        )
        assert r.status_code == 422

    def test_upload_response_contains_filename(self):
        data = json.dumps([make_subject()]).encode()
        r    = client.post(
            "/api/v1/upload/subjects",
            files={"file": ("myfile.json", io.BytesIO(data), "application/json")},
        )
        assert r.json()["filename"] == "myfile.json"


# ════════════════════════════════════════════════════════════════
# 5. EXPORT — CSV
# ════════════════════════════════════════════════════════════════

class TestExportCSV:
    """Integration tests for POST /api/v1/export/csv"""

    def test_returns_200(self):
        r = client.post("/api/v1/export/csv", json=make_export_payload())
        assert r.status_code == 200

    def test_content_type_is_csv(self):
        r = client.post("/api/v1/export/csv", json=make_export_payload())
        assert "text/csv" in r.headers["content-type"]

    def test_content_disposition_is_attachment(self):
        r = client.post("/api/v1/export/csv", json=make_export_payload())
        assert "attachment" in r.headers["content-disposition"]

    def test_filename_contains_timetable_id_prefix(self):
        r        = client.post("/api/v1/export/csv", json=make_export_payload())
        cd       = r.headers["content-disposition"]
        assert "timetable_" in cd

    def test_csv_contains_subject_data(self):
        """Subject code and name must appear in the CSV content."""
        r    = client.post("/api/v1/export/csv", json=make_export_payload())
        text = r.content.decode("utf-8-sig")
        assert "CS101"           in text
        assert "Data Structures" in text

    def test_csv_has_header_row(self):
        """CSV must include a recognisable header row."""
        r    = client.post("/api/v1/export/csv", json=make_export_payload())
        text = r.content.decode("utf-8-sig")
        assert "Subject Code" in text or "subject_id" in text.lower()

    def test_csv_has_metadata_block(self):
        """CSV must include a # metadata block at the top."""
        r    = client.post("/api/v1/export/csv", json=make_export_payload())
        text = r.content.decode("utf-8-sig")
        assert "ClashZero" in text

    def test_multiple_subjects_all_present(self):
        schedule = [
            make_scheduled_slot("CS101", "Data Structures", day=1, slot=1),
            make_scheduled_slot("MA201", "Linear Algebra",  day=1, slot=2),
            make_scheduled_slot("PH301", "Quantum Physics", day=2, slot=1),
        ]
        r    = client.post("/api/v1/export/csv", json=make_export_payload(schedule=schedule))
        text = r.content.decode("utf-8-sig")
        assert "CS101" in text
        assert "MA201" in text
        assert "PH301" in text

    def test_empty_schedule_rejected(self):
        payload = make_export_payload()
        payload["schedule"] = []
        r = client.post("/api/v1/export/csv", json=payload)
        assert r.status_code == 422


# ════════════════════════════════════════════════════════════════
# 6. EXPORT — PDF
# ════════════════════════════════════════════════════════════════

class TestExportPDF:
    """Integration tests for POST /api/v1/export/pdf"""

    def test_returns_200(self):
        r = client.post("/api/v1/export/pdf", json=make_export_payload())
        assert r.status_code == 200

    def test_content_type_is_pdf(self):
        r = client.post("/api/v1/export/pdf", json=make_export_payload())
        assert r.headers["content-type"] == "application/pdf"

    def test_content_disposition_is_attachment(self):
        r = client.post("/api/v1/export/pdf", json=make_export_payload())
        assert "attachment" in r.headers["content-disposition"]

    def test_pdf_magic_bytes(self):
        """%PDF- magic bytes must be present at the start of the response."""
        r = client.post("/api/v1/export/pdf", json=make_export_payload())
        assert r.content[:5] == b"%PDF-"

    def test_pdf_is_non_empty(self):
        r = client.post("/api/v1/export/pdf", json=make_export_payload())
        assert len(r.content) > 1024   # a real PDF is at least 1 KB

    def test_custom_title_accepted(self):
        """Custom title field must not cause errors."""
        payload = make_export_payload(title="Semester 2 Final Exams 2025")
        r       = client.post("/api/v1/export/pdf", json=payload)
        assert r.status_code == 200

    def test_multiple_subjects_exported(self):
        schedule = [
            make_scheduled_slot("CS101", day=1, slot=1),
            make_scheduled_slot("MA201", day=1, slot=2),
            make_scheduled_slot("PH301", day=2, slot=1),
        ]
        r = client.post("/api/v1/export/pdf", json=make_export_payload(schedule=schedule))
        assert r.status_code == 200
        assert r.content[:5] == b"%PDF-"

    def test_empty_schedule_rejected(self):
        payload = make_export_payload()
        payload["schedule"] = []
        r = client.post("/api/v1/export/pdf", json=payload)
        assert r.status_code == 422


# ════════════════════════════════════════════════════════════════
# 7. CSV EXPORT UTILITY — UNIT TESTS
# ════════════════════════════════════════════════════════════════

class TestCSVExportUtil:
    """Direct unit tests for build_csv_bytes() — no HTTP layer."""

    def _make_slots(self, n: int = 2) -> list[ScheduledSlot]:
        return [
            ScheduledSlot(
                subject_id    = f"CS{100 + i}",
                subject_name  = f"Subject {i}",
                day           = (i // 3) + 1,
                slot          = (i % 3) + 1,
                slot_label    = f"Day {(i // 3) + 1} – Slot {(i % 3) + 1}",
                duration      = 90,
                student_count = 20 + i,
                color         = (i % 3) + 1,
            )
            for i in range(n)
        ]

    def test_returns_bytes(self):
        assert isinstance(build_csv_bytes(self._make_slots()), bytes)

    def test_starts_with_utf8_bom(self):
        """CSV must begin with UTF-8 BOM (EF BB BF) for Excel compatibility."""
        result = build_csv_bytes(self._make_slots())
        assert result[:3] == b"\xef\xbb\xbf"

    def test_contains_subject_id(self):
        result = build_csv_bytes(self._make_slots(1))
        assert b"CS100" in result

    def test_sorted_by_day_then_slot(self):
        """Rows must appear in day → slot ascending order."""
        slots = [
            ScheduledSlot(subject_id="B", subject_name="B", day=2, slot=1,
                          slot_label="D2S1", duration=60, student_count=10, color=1),
            ScheduledSlot(subject_id="A", subject_name="A", day=1, slot=2,
                          slot_label="D1S2", duration=60, student_count=10, color=2),
            ScheduledSlot(subject_id="C", subject_name="C", day=1, slot=1,
                          slot_label="D1S1", duration=60, student_count=10, color=1),
        ]
        text = build_csv_bytes(slots).decode("utf-8-sig")
        pos_c = text.index("C,C")
        pos_a = text.index("A,A")
        pos_b = text.index("B,B")
        assert pos_c < pos_a < pos_b, "Rows not sorted: expected C(D1S1) < A(D1S2) < B(D2S1)"

    def test_empty_schedule_raises_value_error(self):
        with pytest.raises(ValueError, match="empty"):
            build_csv_bytes([])

    def test_metadata_block_present(self):
        text = build_csv_bytes(self._make_slots()).decode("utf-8-sig")
        assert "ClashZero" in text
        assert "Total Exams" in text

    def test_day_separator_blank_rows(self):
        """A blank row must appear between day groups."""
        slots = [
            ScheduledSlot(subject_id="A", subject_name="A", day=1, slot=1,
                          slot_label="D1S1", duration=60, student_count=5, color=1),
            ScheduledSlot(subject_id="B", subject_name="B", day=2, slot=1,
                          slot_label="D2S1", duration=60, student_count=5, color=1),
        ]
        text  = build_csv_bytes(slots).decode("utf-8-sig")
        lines = text.splitlines()
        # Find the data rows and check a blank line exists between them
        data_lines = [l for l in lines if "A,A" in l or "B,B" in l or l.strip() == ""]
        assert "" in data_lines, "No blank separator row found between day groups."


# ════════════════════════════════════════════════════════════════
# 8. PDF EXPORT UTILITY — UNIT TESTS
# ════════════════════════════════════════════════════════════════

class TestPDFExportUtil:
    """Direct unit tests for build_pdf_bytes() — no HTTP layer."""

    def _make_slots(self, n: int = 2) -> list[ScheduledSlot]:
        return [
            ScheduledSlot(
                subject_id    = f"CS{100 + i}",
                subject_name  = f"Subject {i}",
                day           = (i // 3) + 1,
                slot          = (i % 3) + 1,
                slot_label    = f"Day {(i // 3) + 1} – Morning",
                duration      = 90,
                student_count = 25,
                color         = (i % 3) + 1,
            )
            for i in range(n)
        ]

    def test_returns_bytes(self):
        assert isinstance(build_pdf_bytes(self._make_slots()), bytes)

    def test_starts_with_pdf_magic(self):
        """Valid PDF must start with %PDF-."""
        result = build_pdf_bytes(self._make_slots())
        assert result[:5] == b"%PDF-"

    def test_minimum_size(self):
        """A real PDF with content must be at least 5 KB."""
        result = build_pdf_bytes(self._make_slots())
        assert len(result) > 5 * 1024

    def test_custom_title_does_not_raise(self):
        build_pdf_bytes(self._make_slots(), title="Custom Exam Title 2025")

    def test_empty_schedule_raises_value_error(self):
        with pytest.raises(ValueError, match="empty"):
            build_pdf_bytes([])

    def test_large_schedule_renders(self):
        """20 subjects across multiple days must render without error."""
        result = build_pdf_bytes(self._make_slots(n=20))
        assert result[:5] == b"%PDF-"

    def test_default_title_used_when_not_provided(self):
        """Calling with no title must not raise."""
        build_pdf_bytes(self._make_slots())   # default title="Exam Timetable"

    def test_all_slot_types_render(self):
        """PDF must handle all 6 slot numbers without error."""
        slots = [
            ScheduledSlot(subject_id=f"S{i}", subject_name=f"Subj {i}",
                          day=1, slot=i, slot_label=f"Slot {i}",
                          duration=60, student_count=10, color=i)
            for i in range(1, 7)
        ]
        result = build_pdf_bytes(slots)
        assert result[:5] == b"%PDF-"
