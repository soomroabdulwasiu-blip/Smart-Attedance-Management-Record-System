"""Explicit consent records and revocation for the local Windows biometric pilot."""

from . import db
from .devices import authorize

NOTICE_VERSION = "AMRS-BIOMETRIC-1"
NOTICE = (
    "Face attendance is optional. A face representation will be encrypted for this Windows account and used only to identify you in enrolled classes. "
    "No camera recording is retained. Recognition can be inaccurate, and this system does not verify liveness. "
    "Manual attendance is available. You may withdraw consent and request removal of your face template. "
    "The institution must explain its retention policy before enrollment. Confirm that the student has read this notice and freely agreed."
)


def has_consent(student_id):
    row = db.one(
        "SELECT consent_given FROM biometric_consents WHERE student_id=:id",
        {"id": student_id},
    )
    return bool(row and row["consent_given"] == 1)


def record_consent(user, student_id, agreed):
    authorize(user)
    with db.connection() as connection:
        cur = connection.cursor()
        cur.execute(
            "MERGE INTO biometric_consents b USING(SELECT :id student_id FROM students WHERE student_id=:id AND is_active=1) s ON(b.student_id=s.student_id) WHEN MATCHED THEN UPDATE SET consent_given=:consent,recorded_by=:actor,recorded_at=CURRENT_TIMESTAMP,notice_version=:version WHEN NOT MATCHED THEN INSERT(student_id,consent_given,recorded_by,notice_version) VALUES(:id,:consent,:actor,:version)",
            {
                "id": student_id,
                "consent": int(bool(agreed)),
                "actor": user["user_id"],
                "version": NOTICE_VERSION,
            },
        )
        if cur.rowcount != 1:
            raise ValueError("Choose an active student.")
        if not agreed:
            cur.execute(
                "UPDATE students SET face_enrolled=0 WHERE student_id=:id",
                {"id": student_id},
            )
        db.audit_event(
            cur,
            user,
            "BIOMETRIC_CONSENT_GIVEN" if agreed else "BIOMETRIC_CONSENT_WITHDRAWN",
            student_id,
        )


def revoke(user, student_id):
    # Disable matching transactionally before removing local bytes.
    record_consent(user, student_id, False)
    from .face import FACE_DIR, LEGACY_FACE_DIR, safe_student_id

    safe_student_id(student_id)
    for path in (
        FACE_DIR / (student_id + ".template"),
        FACE_DIR / (student_id + ".image"),
        LEGACY_FACE_DIR / (student_id + ".png"),
    ):
        path.unlink(missing_ok=True)
