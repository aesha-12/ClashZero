from data.database.database import DatabaseManager
from data.constraints.constraint_engine import ConstraintEngine
from core.solver import Solver
from core.graph_builder import GraphBuilder
import json
from typing import Dict, Any

class IntegrationService:
    def __init__(self, db_url: str = "sqlite:///clashzero.db"):
        self.db = DatabaseManager(db_url)

    def generate_timetable(self, academic_year: str) -> Dict[str, Any]:
        """
        Main pipeline for generating the exam timetable.
        """
        # 1. Fetch algorithm input from database
        # This includes subjects, conflicts (via GraphBuilder), slots, rooms, constraints
        input_data = self.db.get_algorithm_input(academic_year)
        
        subjects = input_data['subjects']
        conflicts = input_data['conflicts']
        time_slots = input_data['time_slots']
        rooms = input_data['rooms']
        constraints_data = input_data['constraints']

        # 2. Pass data into Solver
        # Convert conflicts (dict with lists) back to dict with sets for the solver
        graph = {k: set(v) for k, v in conflicts.items()}
        solver = Solver(graph)
        
        # 3. Receive generated schedule
        solver_result = solver.generate_schedule()
        
        if not solver_result['is_valid']:
            return {
                "status": "error",
                "message": "Solver failed to generate a valid clash-free schedule."
            }

        # 4. Call Constraint Engine for Room Allocation and validation
        engine = ConstraintEngine(constraints_data)
        
        # Greedy room allocation
        room_assignments = engine.allocate_rooms(
            solver_result['schedule'], 
            subjects, 
            rooms
        )
        
        final_schedule = {
            "schedule": solver_result['schedule'],
            "room_assignments": room_assignments,
            "num_slots_used": solver_result['num_slots_used'],
            "metadata": {
                "academic_year": academic_year,
                "total_subjects": len(subjects),
                "total_rooms": len(rooms)
            }
        }

        # 5. Validate schedule against hard constraints
        is_hard_valid = engine.validate_hard_constraints(
            final_schedule, 
            subjects, 
            rooms, 
            time_slots
        )
        
        final_schedule['is_valid'] = solver_result['is_valid'] and is_hard_valid
        
        # 6. Save schedule back to database
        self.db.save_schedule(final_schedule)

        # 7. Return final response
        return {
            "status": "success",
            "data": final_schedule
        }

if __name__ == "__main__":
    # Example usage
    service = IntegrationService()
    # Note: This requires the DB to be populated first
    # print(service.generate_timetable("2025-2026"))
