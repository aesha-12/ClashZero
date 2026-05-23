import argparse
from data.database.database import DatabaseManager
from data.mock_data.mock_data import generate_mock_data
from data.integration_service import IntegrationService
import json
import sys

def main():
    parser = argparse.ArgumentParser(description="ClashZero Exam Timetable Generator")
    parser.add_argument("--demo", action="store_true", help="Run full demo")
    parser.add_argument("--init", action="store_true", help="Initialize database")
    parser.add_argument("--generate", action="store_true", help="Generate mock data")
    parser.add_argument("--run", action="store_true", help="Run timetable generation")
    parser.add_argument("--year", default="2025-2026", help="Academic year")
    
    args = parser.parse_args()
    
    db_manager = DatabaseManager()
    
    if args.init or args.demo:
        print("Initializing database...")
        db_manager.init_db()
        
    if args.generate or args.demo:
        print("Generating mock data...")
        session = db_manager.Session()
        generate_mock_data(session)
        session.close()
        
    if args.run or args.demo:
        print(f"Running timetable generation for {args.year}...")
        service = IntegrationService()
        result = service.generate_timetable(args.year)
        
        if result["status"] == "success":
            print("\nTimetable generated successfully!")
            print(f"Slots used: {result['data']['num_slots_used']}")
            print(f"Is valid: {result['data']['is_valid']}")
            
            # Print first 5 assignments
            schedule = result['data']['schedule']
            room_assignments = result['data']['room_assignments']
            print("\nSample Assignments:")
            for i, (subj, slot) in enumerate(list(schedule.items())[:5]):
                room = room_assignments.get(subj, "N/A")
                print(f"  {subj}: {slot} in {room}")
                
            # Export to JSON
            with open("timetable_output.json", "w") as f:
                json.dump(result["data"], f, indent=4)
            print("\nFull timetable exported to timetable_output.json")
        else:
            print(f"Error: {result['message']}")

if __name__ == "__main__":
    main()
