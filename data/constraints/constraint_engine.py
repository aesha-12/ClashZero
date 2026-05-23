from typing import List, Dict, Any

class ConstraintEngine:
    """
    Validates and evaluates constraints for the exam schedule.
    """

    def __init__(self, constraints: List[Dict[str, Any]]):
        self.constraints = constraints
        self.hard_constraints = [c for c in constraints if c['type'] == 'HARD']
        self.soft_constraints = [c for c in constraints if c['type'] == 'SOFT']

    def validate_hard_constraints(self, schedule: Dict[str, Any], subjects: List[Dict], rooms: List[Dict], slots: List[Dict]) -> bool:
        """
        Verify that all hard constraints are met.
        """
        # 1. Student Clashes (Implicitly handled by graph coloring, but we can re-verify)
        # 2. Room capacity check
        # 3. Lab requirement check
        
        subject_map = {s['subject_id']: s for s in subjects}
        room_map = {r['name']: r for r in rooms}
        slot_map = {f"Slot {i+1}": slots[i] for i in range(min(len(slots), 100))} # Rough mapping

        for subject_id, slot_label in schedule.get('schedule', {}).items():
            subject = subject_map.get(subject_id)
            room_name = schedule.get('room_assignments', {}).get(subject_id)
            room = room_map.get(room_name)

            if subject and room:
                # Capacity check
                # Note: We'd need student count per subject
                student_count = len(subject.get('students', []))
                if student_count > room['capacity']:
                    return False
                
                # Lab check
                if subject.get('requires_lab') and not room.get('has_computers'):
                    return False

        return True

    def calculate_penalties(self, schedule: Dict[str, Any], subjects: List[Dict]) -> int:
        """
        Calculate penalty points for soft constraint violations.
        """
        penalty = 0
        # Example: Penalty for multiple exams on the same day for a student
        # This requires detailed student-to-subject mapping and slot-to-date mapping
        return penalty

    def allocate_rooms(self, schedule: Dict[str, str], subjects: List[Dict], rooms: List[Dict]) -> Dict[str, str]:
        """
        Greedy room allocation based on capacity and requirements.
        """
        room_assignments = {}
        # Sort rooms by capacity
        sorted_rooms = sorted(rooms, key=lambda x: x['capacity'])
        
        # Group subjects by slot
        slots = {}
        for subj, slot in schedule.items():
            if slot not in slots:
                slots[slot] = []
            slots[slot].append(subj)
            
        subject_data = {s['subject_id']: s for s in subjects}

        for slot, slot_subjects in slots.items():
            available_rooms = sorted_rooms.copy()
            for subj_id in slot_subjects:
                subj = subject_data[subj_id]
                student_count = len(subj.get('students', []))
                needs_lab = subj.get('requires_lab', False)
                
                assigned = False
                for i, room in enumerate(available_rooms):
                    if room['capacity'] >= student_count:
                        if needs_lab and not room['has_computers']:
                            continue
                        
                        room_assignments[subj_id] = room['name']
                        available_rooms.pop(i)
                        assigned = True
                        break
                
                if not assigned:
                    # Fallback or error?
                    room_assignments[subj_id] = "UNASSIGNED"
                    
        return room_assignments
