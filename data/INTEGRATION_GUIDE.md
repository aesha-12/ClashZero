# Integration Guide - Data & Constraints Module

## For Member 1 (Algorithm)

### Getting Input Data

```python
from database import DatabaseManager

db = DatabaseManager()
algo_input = db.get_algorithm_input("2025-2026")

# algo_input contains:
# - subjects: List of subjects with student counts
# - conflicts: Adjacency list (subject_id -> [conflicting_subject_ids])
# - time_slots: Available slots
# - rooms: Available rooms with capacities
# - constraints: Active constraints from DB
