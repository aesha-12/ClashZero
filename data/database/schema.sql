-- Exam Scheduling System Database Schema
-- Compatible with PostgreSQL and SQLite

-- Departments table
CREATE TABLE IF NOT EXISTS departments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name VARCHAR(100) NOT NULL UNIQUE,
    code VARCHAR(10) NOT NULL UNIQUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Subjects table
CREATE TABLE IF NOT EXISTS subjects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code VARCHAR(20) NOT NULL UNIQUE,
    name VARCHAR(200) NOT NULL,
    department_id INTEGER NOT NULL,
    credits INTEGER DEFAULT 3,
    exam_duration_minutes INTEGER DEFAULT 180,
    requires_computer_lab BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (department_id) REFERENCES departments(id)
);

-- Students table
CREATE TABLE IF NOT EXISTS students (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    roll_number VARCHAR(20) NOT NULL UNIQUE,
    name VARCHAR(100) NOT NULL,
    department_id INTEGER NOT NULL,
    semester INTEGER NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (department_id) REFERENCES departments(id)
);

-- Student-Subject enrollment (many-to-many)
CREATE TABLE IF NOT EXISTS enrollments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id INTEGER NOT NULL,
    subject_id INTEGER NOT NULL,
    academic_year VARCHAR(9) NOT NULL,  -- e.g., "2025-2026"
    UNIQUE(student_id, subject_id, academic_year),
    FOREIGN KEY (student_id) REFERENCES students(id),
    FOREIGN KEY (subject_id) REFERENCES subjects(id)
);

-- Rooms/Venues table
CREATE TABLE IF NOT EXISTS rooms (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name VARCHAR(50) NOT NULL UNIQUE,
    capacity INTEGER NOT NULL,
    building VARCHAR(100),
    floor INTEGER,
    has_computers BOOLEAN DEFAULT FALSE,
    has_projector BOOLEAN DEFAULT TRUE,
    is_accessible BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Time slots table
CREATE TABLE IF NOT EXISTS time_slots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date DATE NOT NULL,
    start_time TIME NOT NULL,
    end_time TIME NOT NULL,
    slot_name VARCHAR(50),  -- e.g., "Morning", "Afternoon"
    is_available BOOLEAN DEFAULT TRUE,
    UNIQUE(date, start_time)
);

-- Constraints table (stores both hard and soft constraints)
CREATE TABLE IF NOT EXISTS constraints (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name VARCHAR(100) NOT NULL,
    constraint_type VARCHAR(10) NOT NULL CHECK (constraint_type IN ('HARD', 'SOFT')),
    category VARCHAR(50) NOT NULL,
    description TEXT,
    parameters JSON,  -- Flexible storage for constraint parameters
    is_active BOOLEAN DEFAULT TRUE,
    priority INTEGER DEFAULT 50,  -- 1-100, higher = more important
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Scheduled exams (output table)
CREATE TABLE IF NOT EXISTS scheduled_exams (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    subject_id INTEGER NOT NULL,
    room_id INTEGER NOT NULL,
    time_slot_id INTEGER NOT NULL,
    schedule_version INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (subject_id) REFERENCES subjects(id),
    FOREIGN KEY (room_id) REFERENCES rooms(id),
    FOREIGN KEY (time_slot_id) REFERENCES time_slots(id)
);

-- Schedule history (for storing previous schedules)
CREATE TABLE IF NOT EXISTS schedule_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    version INTEGER NOT NULL,
    department_id INTEGER,
    academic_year VARCHAR(9) NOT NULL,
    exam_period VARCHAR(50),  -- e.g., "Mid-Semester", "Final"
    schedule_data JSON NOT NULL,
    generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    generated_by VARCHAR(100),
    notes TEXT,
    FOREIGN KEY (department_id) REFERENCES departments(id)
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_enrollments_student ON enrollments(student_id);
CREATE INDEX IF NOT EXISTS idx_enrollments_subject ON enrollments(subject_id);
CREATE INDEX IF NOT EXISTS idx_subjects_department ON subjects(department_id);
CREATE INDEX IF NOT EXISTS idx_scheduled_exams_slot ON scheduled_exams(time_slot_id);
CREATE INDEX IF NOT EXISTS idx_time_slots_date ON time_slots(date);
