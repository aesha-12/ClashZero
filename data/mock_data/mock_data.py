from faker import Faker
import random
from data.database.models import Department, Subject, Student, Enrollment, Room, TimeSlot, Constraint
from sqlalchemy.orm import Session
from datetime import date, time, timedelta

fake = Faker()

def generate_mock_data(session: Session):
    # 1. Departments
    depts = []
    dept_data = [
        ("Computer Science", "CS"),
        ("Mathematics", "MA"),
        ("Physics", "PH"),
        ("English", "EN")
    ]
    for name, code in dept_data:
        dept = Department(name=name, code=code)
        session.add(dept)
        depts.append(dept)
    session.flush()

    # 2. Subjects
    subjects = []
    for dept in depts:
        for i in range(1, 6):
            subj = Subject(
                code=f"{dept.code}{100+i}",
                name=f"{dept.name} Course {i}",
                department_id=dept.id,
                credits=3,
                exam_duration_minutes=120,
                requires_computer_lab=(random.random() < 0.2)
            )
            session.add(subj)
            subjects.append(subj)
    session.flush()

    # 3. Students
    students = []
    for dept in depts:
        for i in range(1, 51):
            student = Student(
                roll_number=f"{dept.code}{2025}{i:03d}",
                name=fake.name(),
                department_id=dept.id,
                semester=random.randint(1, 8)
            )
            session.add(student)
            students.append(student)
    session.flush()

    # 4. Enrollments (Mocking clashes)
    for student in students:
        # Each student takes 3-5 random subjects
        chosen_subjects = random.sample(subjects, random.randint(3, 5))
        for subj in chosen_subjects:
            enrollment = Enrollment(
                student_id=student.id,
                subject_id=subj.id,
                academic_year="2025-2026"
            )
            session.add(enrollment)
    
    # 5. Rooms
    room_data = [
        ("Hall A", 100, "Main Bldg", 1, False),
        ("Hall B", 150, "Main Bldg", 1, False),
        ("Lab 1", 30, "Tech Bldg", 2, True),
        ("Lab 2", 30, "Tech Bldg", 2, True),
        ("Room 101", 40, "Arts Bldg", 1, False),
    ]
    for name, cap, bldg, floor, has_comp in room_data:
        room = Room(
            name=name, 
            capacity=cap, 
            building=bldg, 
            floor=floor, 
            has_computers=has_comp
        )
        session.add(room)

    # 6. Time Slots
    start_date = date(2026, 5, 25)
    for i in range(5): # 5 days
        curr_date = start_date + timedelta(days=i)
        # Morning slot
        session.add(TimeSlot(
            date=curr_date,
            start_time=time(9, 0),
            end_time=time(12, 0),
            slot_name="Morning"
        ))
        # Afternoon slot
        session.add(TimeSlot(
            date=curr_date,
            start_time=time(14, 0),
            end_time=time(17, 0),
            slot_name="Afternoon"
        ))

    # 7. Constraints
    session.add(Constraint(
        name="No Student Clashes",
        constraint_type="HARD",
        category="CLASH",
        description="A student cannot have two exams at the same time."
    ))
    session.add(Constraint(
        name="Room Capacity",
        constraint_type="HARD",
        category="CAPACITY",
        description="Number of students must not exceed room capacity."
    ))

    session.commit()
    print("Mock data generated successfully.")
