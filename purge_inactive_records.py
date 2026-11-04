"""Compatibility entry point for dry-run-first, approval-gated maintenance."""
from amrs.maintenance import delete_face_photos,main,purge_inactive_records

if __name__=='__main__':raise SystemExit(main())
