import sqlite3

from fastapi import APIRouter, Depends

from app.deps import get_db, require_admin
from app.helpers import audit_log_row_to_dict
from app.schemas import AuditLogOut

router = APIRouter(prefix="/api/audit-logs", tags=["audit"])


@router.get("", response_model=list[AuditLogOut])
def list_audit_logs(
    admin: sqlite3.Row = Depends(require_admin),
    db: sqlite3.Connection = Depends(get_db),
):
    """
    Read-only. Entries are written automatically by write_audit_log() inside
    the other routers whenever a sensitive action happens — there is no
    endpoint to create or edit a log entry directly, to preserve integrity.
    """
    rows = db.execute("SELECT * FROM audit_logs ORDER BY timestamp DESC").fetchall()
    return [audit_log_row_to_dict(r) for r in rows]
