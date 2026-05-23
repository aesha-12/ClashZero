from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, Date, Time, Text, JSON, DateTime, UniqueConstraint, CheckConstraint
from sqlalchemy.orm import relationship, declarative_base
from sqlalchemy.sql import func
import datetime

Base = declarative_base()

class Department(Base):
    __tablename__ = 'departments'
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False, unique=True)
    code = Column(String(10), nullable=False, unique=True)
    created_at = Column(DateTime, server_default=func.now())

    subjects = relationship("Subject", back_populates="department")
    students = relationship("Student", back_populates="department")

class Subject(Base):
    __tablename__ = 'subjects'
    id = Column(Integer, primary_key=True, autoincrement=True)
    code = Column(String(20), nullable=False, unique=True)
    name = Column(String(200), nullable=False)
    department_id = Column(Integer, ForeignKey('departments.id'), nullable=False)
    credits = Column(Integer, default=3)
    exam_duration_minutes = Column(Integer, default=180)
    requires_computer_lab = Column(Boolean, default=False)
    created_at = Column(DateTime, server_default=func.now())

    department = relationship("Department", back_populates="subjects")
    enrollments = relationship("Enrollment", back_populates="subject")
    scheduled_exams = relationship("ScheduledExam", back_populates="subject")

class Student(Base):
    __tablename__ = 'students'
    id = Column(Integer, primary_key=True, autoincrement=True)
    roll_number = Column(String(20), nullable=False, unique=True)
    name = Column(String(100), nullable=False)
    department_id = Column(Integer, ForeignKey('departments.id'), nullable=False)
    semester = Column(Integer, nullable=False)
    created_at = Column(DateTime, server_default=func.now())

    department = relationship("Department", back_populates="students")
    enrollments = relationship("Enrollment", back_populates="student")

class Enrollment(Base):
    __tablename__ = 'enrollments'
    id = Column(Integer, primary_key=True, autoincrement=True)
    student_id = Column(Integer, ForeignKey('students.id'), nullable=False)
    subject_id = Column(Integer, ForeignKey('subjects.id'), nullable=False)
    academic_year = Column(String(9), nullable=False)  # e.g., "2025-2026"

    __table_args__ = (UniqueConstraint('student_id', 'subject_id', 'academic_year', name='uix_enrollment'),)

    student = relationship("Student", back_populates="enrollments")
    subject = relationship("Subject", back_populates="enrollments")

class Room(Base):
    __tablename__ = 'rooms'
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(50), nullable=False, unique=True)
    capacity = Column(Integer, nullable=False)
    building = Column(String(100))
    floor = Column(Integer)
    has_computers = Column(Boolean, default=False)
    has_projector = Column(Boolean, default=True)
    is_accessible = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.now())

    scheduled_exams = relationship("ScheduledExam", back_populates="room")

class TimeSlot(Base):
    __tablename__ = 'time_slots'
    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(Date, nullable=False)
    start_time = Column(Time, nullable=False)
    end_time = Column(Time, nullable=False)
    slot_name = Column(String(50))  # e.g., "Morning", "Afternoon"
    is_available = Column(Boolean, default=True)

    __table_args__ = (UniqueConstraint('date', 'start_time', name='uix_timeslot'),)

    scheduled_exams = relationship("ScheduledExam", back_populates="time_slot")

class Constraint(Base):
    __tablename__ = 'constraints'
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    constraint_type = Column(String(10), nullable=False) # 'HARD', 'SOFT'
    category = Column(String(50), nullable=False)
    description = Column(Text)
    parameters = Column(JSON)
    is_active = Column(Boolean, default=True)
    priority = Column(Integer, default=50)
    created_at = Column(DateTime, server_default=func.now())

    __table_args__ = (CheckConstraint("constraint_type IN ('HARD', 'SOFT')", name='check_constraint_type'),)

class ScheduledExam(Base):
    __tablename__ = 'scheduled_exams'
    id = Column(Integer, primary_key=True, autoincrement=True)
    subject_id = Column(Integer, ForeignKey('subjects.id'), nullable=False)
    room_id = Column(Integer, ForeignKey('rooms.id'), nullable=False)
    time_slot_id = Column(Integer, ForeignKey('time_slots.id'), nullable=False)
    schedule_version = Column(Integer, default=1)
    created_at = Column(DateTime, server_default=func.now())

    subject = relationship("Subject", back_populates="scheduled_exams")
    room = relationship("Room", back_populates="scheduled_exams")
    time_slot = relationship("TimeSlot", back_populates="scheduled_exams")

class ScheduleHistory(Base):
    __tablename__ = 'schedule_history'
    id = Column(Integer, primary_key=True, autoincrement=True)
    version = Column(Integer, nullable=False)
    department_id = Column(Integer, ForeignKey('departments.id'))
    academic_year = Column(String(9), nullable=False)
    exam_period = Column(String(50))
    schedule_data = Column(JSON, nullable=False)
    generated_at = Column(DateTime, server_default=func.now())
    generated_by = Column(String(100))
    notes = Column(Text)
