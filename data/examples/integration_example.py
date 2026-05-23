from data.integration_service import IntegrationService
from data.database.database import DatabaseManager
from data.mock_data.mock_data import generate_mock_data
import json

def run_example():
    # 1. Setup DB and Data
    db_manager = DatabaseManager("sqlite:///example.db")
    session = db_manager.Session()
    generate_mock_data(session)
    session.close()

    # 2. Run Integration Service
    service = IntegrationService("sqlite:///example.db")
    result = service.generate_timetable("2025-2026")

    if result["status"] == "success":
        print("Integration successful!")
        print(json.dumps(result["data"], indent=2))
    else:
        print(f"Integration failed: {result['message']}")

if __name__ == "__main__":
    run_example()
