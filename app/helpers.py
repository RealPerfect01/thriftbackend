import sqlite3
import time
import uuid
from typing import Optional


def now_ms() -> int:
    return int(time.time() * 1000)


def new_reference(prefix: str = "THRF") -> str:
    tail = str(now_ms())[-4:]
    rand = uuid.uuid4().hex[:5].upper()
    return f"{prefix}-{tail}-{rand}"


def write_audit_log(
    db: sqlite3.Connection,
    actor_name: str,
    actor_role: str,
    action: str,
    details: str,
) -> None:
    """
    Internal helper — never exposed as its own endpoint. Every write-endpoint
    in the routers calls this so the audit trail is generated automatically,
    the same way ThriftRepository.kt did on the Android side.
    """
    db.execute(
        "INSERT INTO audit_logs (actorName, actorRole, action, details, timestamp) "
        "VALUES (?, ?, ?, ?, ?)",
        (actor_name, actor_role, action, details, now_ms()),
    )


def create_notification(
    db: sqlite3.Connection,
    recipient_role: str,
    title: str,
    message: str,
    user_id: Optional[int] = None,
) -> None:
    db.execute(
        "INSERT INTO notifications (recipientRole, userId, title, message, isRead, timestamp) "
        "VALUES (?, ?, ?, ?, 0, ?)",
        (recipient_role, user_id, title, message, now_ms()),
    )


def user_row_to_dict(row: sqlite3.Row) -> dict:
    """Converts a `users` row to a safe dict — never includes passwordHash."""
    return {
        "id": row["id"],
        "fullName": row["fullName"],
        "phoneNumber": row["phoneNumber"],
        "email": row["email"],
        "homeAddress": row["homeAddress"],
        "idNumber": row["idNumber"],
        "thriftPlan": row["thriftPlan"],
        "role": row["role"],
        "status": row["status"],
        "savingsBalance": row["savingsBalance"],
        "targetAmount": row["targetAmount"],
        "createdAt": row["createdAt"],
    }


def transaction_row_to_dict(row: sqlite3.Row) -> dict:
    return dict(row)


def notification_row_to_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    d["isRead"] = bool(d["isRead"])
    return d


def audit_log_row_to_dict(row: sqlite3.Row) -> dict:
    return dict(row)
