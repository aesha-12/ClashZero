import pytest
from data.integration_service import IntegrationService
from data.database.database import DatabaseManager
from data.mock_data.mock_data import generate_mock_data
import os

@pytest.fixture
def test_db():
    db_path = "test_clashzero.db"
    if os.path.exists(db_path):
        os.remove(db_path)
    
    db_manager = DatabaseManager(f"sqlite:///{db_path}")
    session = db_manager.Session()
    generate_mock_data(session)
    session.close()
    
    yield f"sqlite:///{db_path}"
    
    if os.path.exists(db_path):
        os.remove(db_path)

def test_integration_pipeline(test_db):
    service = IntegrationService(test_db)
    result = service.generate_timetable("2025-2026")
    
    assert result["status"] == "success"
    assert "data" in result
    assert result["data"]["is_valid"] is True
    assert result["data"]["num_slots_used"] > 0
    assert len(result["data"]["schedule"]) > 0

def test_room_allocation_stress(test_db):
    # This could be expanded to test larger datasets
    service = IntegrationService(test_db)
    result = service.generate_timetable("2025-2026")
    
    room_assignments = result["data"]["room_assignments"]
    # Ensure every subject in the schedule has a room
    for subj in result["data"]["schedule"]:
        assert subj in room_assignments
        assert room_assignments[subj] != "UNASSIGNED"
