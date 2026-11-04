CREATE TABLE academic_classes (
 class_id VARCHAR2(36) PRIMARY KEY,
 class_name VARCHAR2(120) NOT NULL,
 dept_id NUMBER NOT NULL REFERENCES departments(dept_id),
 semester NUMBER NOT NULL CHECK (semester BETWEEN 1 AND 16),
 section_name VARCHAR2(40) NOT NULL,
 academic_year NUMBER(4) NOT NULL,
 is_active NUMBER(1) DEFAULT 1 NOT NULL CHECK (is_active IN (0,1)),
 created_at TIMESTAMP DEFAULT SYS_EXTRACT_UTC(SYSTIMESTAMP) NOT NULL,
 CONSTRAINT uq_academic_class UNIQUE (dept_id,semester,section_name,academic_year)
)
/
ALTER TABLE courses ADD class_id VARCHAR2(36) REFERENCES academic_classes(class_id)
/
CREATE INDEX ix_courses_class ON courses(class_id)
/
