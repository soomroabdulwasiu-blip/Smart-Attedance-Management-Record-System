CREATE TABLE teacher_signup_requests (
  request_id VARCHAR2(36) PRIMARY KEY, full_name VARCHAR2(200) NOT NULL,
  email VARCHAR2(255) NOT NULL, password_hash VARCHAR2(255) NOT NULL,
  department VARCHAR2(200), status VARCHAR2(16) DEFAULT 'PENDING' NOT NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL, resolved_at TIMESTAMP,
  resolved_by VARCHAR2(36), CONSTRAINT ck_teacher_request_status CHECK (status IN ('PENDING','APPROVED','REJECTED')) )
/
CREATE TABLE attendance_correction_requests (
  request_id VARCHAR2(36) PRIMARY KEY, attendance_id NUMBER NOT NULL,
  student_id VARCHAR2(36) NOT NULL, requested_status VARCHAR2(10) NOT NULL,
  reason VARCHAR2(500) NOT NULL, status VARCHAR2(16) DEFAULT 'PENDING' NOT NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL, resolved_at TIMESTAMP,
  resolved_by VARCHAR2(36), CONSTRAINT fk_correction_attendance FOREIGN KEY (attendance_id) REFERENCES attendance(attendance_id) ON DELETE CASCADE,
  CONSTRAINT fk_correction_student FOREIGN KEY (student_id) REFERENCES students(student_id) ON DELETE CASCADE,
  CONSTRAINT ck_correction_state CHECK (status IN ('PENDING','APPROVED','REJECTED')),
  CONSTRAINT ck_correction_target CHECK (requested_status IN ('PRESENT','ABSENT','LATE')) )
/
