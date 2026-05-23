# ClashZero - AI-Based Exam Timetable Generator

ClashZero is a modular system for generating clash-free exam timetables using graph coloring algorithms and constraint satisfaction.

## Project Structure

- `core/`: Core algorithm (Graph building, Solver, Validation).
- `data/`: Data management layer.
    - `database/`: SQLAlchemy models and Database Manager.
    - `constraints/`: Constraint Engine for room allocation and rule validation.
    - `mock_data/`: Utilities for generating test data.
    - `integration_service.py`: Orchestrates the flow between modules.

## Setup Instructions

1. **Install Dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Initialize and Run Demo:**
   This will create the database, generate mock data, and run the timetable generator.
   ```bash
   python -m data.main --demo
   ```

## Running Components Individually

- **Initialize Database:**
  ```bash
  python -m data.main --init
  ```

- **Generate Mock Data:**
  ```bash
  python -m data.main --generate
  ```

- **Run Timetable Generator:**
  ```bash
  python -m data.main --run --year "2025-2026"
  ```

## Testing

Run tests using pytest:
```bash
pytest data/tests
```

## JSON Output

The generator produces a `timetable_output.json` file with the following structure:
```json
{
    "schedule": {
        "CS101": "Slot 1",
        "MA101": "Slot 1",
        "PH101": "Slot 2"
    },
    "room_assignments": {
        "CS101": "Hall A",
        "MA101": "Hall B",
        "PH101": "Lab 1"
    },
    "num_slots_used": 2,
    "is_valid": true,
    "metadata": { ... }
}
```
