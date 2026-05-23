from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from data.database.models import Base, Subject, Student, Enrollment, Room, TimeSlot, Constraint, ScheduledExam, Department
from core.graph_builder import GraphBuilder
import json

class DatabaseManager:
    def __init__(self, db_url="sqlite:///clashzero.db"):
        self.engine = create_engine(db_url)
        self.Session = sessionmaker(bind=self.engine)
        self.init_db()

    def init_db(self):
        Base.metadata.create_all(self.engine)

    def get_algorithm_input(self, academic_year: str):
        session = self.Session()
        try:
            # Fetch subjects for the academic year
            subjects_query = session.query(Subject).join(Enrollment).filter(Enrollment.academic_year == academic_year).distinct().all()
            
            subjects_list = []
            for s in subjects_query:
                # Get student IDs for this subject
                student_ids = [str(e.student_id) for e in s.enrollments if e.academic_year == academic_year]
                subjects_list.append({
                    "subject_id": s.code,
                    "subject_name": s.name,
                    "students": student_ids,
                    "duration": s.exam_duration_minutes,
                    "requires_lab": s.requires_computer_lab
                })

            # Fetch slots
            slots = session.query(TimeSlot).filter(TimeSlot.is_available == True).all()
            slots_list = [{
                "id": sl.id,
                "name": sl.slot_name,
                "date": str(sl.date),
                "start": str(sl.start_time),
                "end": str(sl.end_time)
            } for sl in slots]

            # Fetch rooms
            rooms = session.query(Room).all()
            rooms_list = [{
                "id": r.id,
                "name": r.name,
                "capacity": r.capacity,
                "has_computers": r.has_computers
            } for r in rooms]

            # Fetch constraints
            constraints = session.query(Constraint).filter(Constraint.is_active == True).all()
            constraints_list = [{
                "name": c.name,
                "type": c.constraint_type,
                "category": c.category,
                "params": c.parameters
            } for c in constraints]

            # Use GraphBuilder to generate conflicts
            # This follows the "centralize logic" requirement
            conflicts = GraphBuilder.build_graph(subjects_list)
            
            # Convert set to list for JSON compatibility if needed
            conflicts_json = {k: list(v) for k, v in conflicts.items()}

            return {
                "subjects": subjects_list,
                "conflicts": conflicts_json,
                "time_slots": slots_list,
                "rooms": rooms_list,
                "constraints": constraints_list
            }
        finally:
            session.close()

    def save_schedule(self, schedule_result: dict):
        """
        Expects schedule_result in format:
        {
            "schedule": {"CS101": "Slot 1", ...},
            "room_assignments": {"CS101": "Room A", ...},
            "metadata": {...}
        }
        """
        session = self.Session()
        try:
            # Clear existing schedule or handle versioning?
            # For now, let's just add new entries
            for subject_code, slot_name in schedule_result["schedule"].items():
                subject = session.query(Subject).filter(Subject.code == subject_code).first()
                # Find the slot_id from slot_name (e.g. "Slot 1" -> might need a mapping)
                # Actually, our solver uses "Slot 1", "Slot 2". 
                # We need to map these back to actual TimeSlot IDs.
                
                # For this demo, we'll assume a simple mapping or just store the slot name in a history table
                pass
            
            # Implementation for actual saving to scheduled_exams table would go here
            # But we need the mapping from "Slot 1" to actual TimeSlot objects.
            session.commit()
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()
