import sqlite3

from fastapi import APIRouter, Depends, HTTPException

from app.deps import get_current_user, get_db, require_admin
from app.helpers import notification_row_to_dict
from app.schemas import NotificationOut

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


@router.get("/admin", response_model=list[NotificationOut])
def get_admin_notifications(
    admin: sqlite3.Row = Depends(require_admin),
    db: sqlite3.Connection = Depends(get_db),
):
    rows = db.execute(
        "SELECT * FROM notifications WHERE recipientRole IN ('ALL','ADMIN') ORDER BY timestamp DESC"
    ).fetchall()
    return [notification_row_to_dict(r) for r in rows]


@router.get("/me", response_model=list[NotificationOut])
def get_my_notifications(
    user: sqlite3.Row = Depends(get_current_user),
    db: sqlite3.Connection = Depends(get_db),
):
    rows = db.execute(
        "SELECT * FROM notifications "
        "WHERE recipientRole IN ('ALL','CUSTOMER') AND (userId IS NULL OR userId = ?) "
        "ORDER BY timestamp DESC",
        (user["id"],),
    ).fetchall()
    return [notification_row_to_dict(r) for r in rows]


@router.put("/{notification_id}/read", response_model=dict)
def mark_notification_read(
    notification_id: int,
    user: sqlite3.Row = Depends(get_current_user),
    db: sqlite3.Connection = Depends(get_db),
):
    row = db.execute("SELECT id FROM notifications WHERE id = ?", (notification_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Notification not found.")
    db.execute("UPDATE notifications SET isRead = 1 WHERE id = ?", (notification_id,))
    db.commit()
    return {"message": "Marked as read."}


@router.delete("/{notification_id}", response_model=dict)
def delete_notification(
    notification_id: int,
    user: sqlite3.Row = Depends(get_current_user),
    db: sqlite3.Connection = Depends(get_db),
):
    db.execute("DELETE FROM notifications WHERE id = ?", (notification_id,))
    db.commit()
    return {"message": "Notification dismissed."}


@router.put("/admin/read-all", response_model=dict)
def mark_all_admin_notifications_read(
    admin: sqlite3.Row = Depends(require_admin),
    db: sqlite3.Connection = Depends(get_db),
):
    db.execute("UPDATE notifications SET isRead = 1 WHERE recipientRole IN ('ALL','ADMIN')")
    db.commit()
    return {"message": "All admin alerts marked as read."}


@router.delete("/admin/clear", response_model=dict)
def clear_admin_notifications(
    admin: sqlite3.Row = Depends(require_admin),
    db: sqlite3.Connection = Depends(get_db),
):
    db.execute("DELETE FROM notifications WHERE recipientRole IN ('ALL','ADMIN')")
    db.commit()
    return {"message": "All admin alerts cleared."}


@router.put("/me/read-all", response_model=dict)
def mark_all_my_notifications_read(
    user: sqlite3.Row = Depends(get_current_user),
    db: sqlite3.Connection = Depends(get_db),
):
    db.execute(
        "UPDATE notifications SET isRead = 1 "
        "WHERE recipientRole IN ('ALL','CUSTOMER') AND (userId IS NULL OR userId = ?)",
        (user["id"],),
    )
    db.commit()
    return {"message": "All notifications marked as read."}


@router.delete("/me/clear", response_model=dict)
def clear_my_notifications(
    user: sqlite3.Row = Depends(get_current_user),
    db: sqlite3.Connection = Depends(get_db),
):
    db.execute(
        "DELETE FROM notifications "
        "WHERE recipientRole IN ('ALL','CUSTOMER') AND (userId IS NULL OR userId = ?)",
        (user["id"],),
    )
    db.commit()
    return {"message": "All notifications cleared."}
