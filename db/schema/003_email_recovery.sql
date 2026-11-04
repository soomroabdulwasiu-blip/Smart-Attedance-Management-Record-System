CREATE TABLE email_password_resets (
 request_id VARCHAR2(36) PRIMARY KEY,
 user_type VARCHAR2(10) NOT NULL CHECK (user_type IN ('STUDENT','TEACHER')),
 user_id VARCHAR2(36) NOT NULL,
 user_email VARCHAR2(254) NOT NULL,
 code_hash VARCHAR2(100) NOT NULL,
 password_version VARCHAR2(100) NOT NULL,
 created_at TIMESTAMP DEFAULT SYS_EXTRACT_UTC(SYSTIMESTAMP) NOT NULL,
 expires_at TIMESTAMP NOT NULL,
 attempts NUMBER DEFAULT 0 NOT NULL,
 status VARCHAR2(12) NOT NULL CHECK (status IN ('SENDING','SENT','USED','FAILED','INVALIDATED','LOCKED')),
 notification VARCHAR2(12),
 resolved_at TIMESTAMP)
/
CREATE INDEX ix_email_reset_account ON email_password_resets(user_type,user_id,created_at)
/
