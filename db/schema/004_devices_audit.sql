CREATE TABLE camera_devices (
 device_id VARCHAR2(36) PRIMARY KEY,
 name VARCHAR2(120) NOT NULL,
 device_type VARCHAR2(24) NOT NULL CHECK (device_type IN ('builtin','usb','rtsp','http','raspberry_pi','esp32','mock')),
 endpoint VARCHAR2(1000) NOT NULL,
 enabled NUMBER(1) DEFAULT 1 NOT NULL CHECK (enabled IN (0,1)),
 is_active_source NUMBER(1) DEFAULT 0 NOT NULL CHECK (is_active_source IN (0,1)),
 config_json VARCHAR2(4000) DEFAULT '{}' NOT NULL,
 status VARCHAR2(24) DEFAULT 'DISCONNECTED' NOT NULL,
 last_error VARCHAR2(500), last_connected TIMESTAMP,
 created_by VARCHAR2(36) NOT NULL REFERENCES users(user_id),
 created_at TIMESTAMP DEFAULT SYS_EXTRACT_UTC(SYSTIMESTAMP) NOT NULL,
 updated_at TIMESTAMP DEFAULT SYS_EXTRACT_UTC(SYSTIMESTAMP) NOT NULL,
 CONSTRAINT ck_camera_active_enabled CHECK (is_active_source=0 OR enabled=1)
)
/
CREATE UNIQUE INDEX uq_camera_active_source ON camera_devices(CASE WHEN is_active_source=1 THEN 1 END)
/
CREATE TABLE app_audit (
 event_id VARCHAR2(36) PRIMARY KEY,
 actor_id VARCHAR2(36), actor_role VARCHAR2(16) NOT NULL,
 action VARCHAR2(64) NOT NULL, entity_id VARCHAR2(64),
 detail VARCHAR2(1000),
 created_at TIMESTAMP DEFAULT SYS_EXTRACT_UTC(SYSTIMESTAMP) NOT NULL
)
/
CREATE INDEX ix_app_audit_created ON app_audit(created_at)
/
CREATE TABLE biometric_consents (
 student_id VARCHAR2(36) PRIMARY KEY REFERENCES students(student_id) ON DELETE CASCADE,
 consent_given NUMBER(1) NOT NULL CHECK (consent_given IN (0,1)),
 recorded_by VARCHAR2(36) NOT NULL REFERENCES users(user_id),
 recorded_at TIMESTAMP DEFAULT SYS_EXTRACT_UTC(SYSTIMESTAMP) NOT NULL,
 notice_version VARCHAR2(32) NOT NULL
)
/
CREATE TABLE attendance_settings (
 setting_key VARCHAR2(64) PRIMARY KEY,
 value_json VARCHAR2(4000) NOT NULL,
 updated_by VARCHAR2(36) REFERENCES users(user_id),
 updated_at TIMESTAMP DEFAULT SYS_EXTRACT_UTC(SYSTIMESTAMP) NOT NULL
)
/
