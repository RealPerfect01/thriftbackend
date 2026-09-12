import sqlite3

from fastapi import APIRouter, Depends, HTTPException

from app.deps import get_current_user, get_db
from app.helpers import user_row_to_dict, write_audit_log
from app.schemas import ChangePasswordRequest, UserOut, UserUpdate
from app.security import hash_password, verify_password

router = APIRouter(prefix="/api/me", tags=["me"])


@router.get("", response_model=UserOut)
def get_my_profile(user: sqlite3.Row = Depends(get_current_user)):
    return user_row_to_dict(user)


@router.put("", response_model=UserOut)
def update_my_profile(
    payload: UserUpdate,
    user: sqlite3.Row = Depends(get_current_user),
    db: sqlite3.Connection = Depends(get_db),
):
    fields = payload.model_dump(exclude_unset=True, exclude={"thriftPlan", "targetAmount"})
    if not fields:
        return user_row_to_dict(user)

    set_clause = ", ".join(f"{k} = ?" for k in fields)
    db.execute(
        f"UPDATE users SET {set_clause} WHERE id = ?",
        (*fields.values(), user["id"]),
    )
    write_audit_log(
        db, user["fullName"], user["role"], "PROFILE_UPDATE",
        f"Profile details updated for {user['fullName']} ({user['email']})",
    )
    db.commit()

    updated = db.execute("SELECT * FROM users WHERE id = ?", (user["id"],)).fetchone()
    return user_row_to_dict(updated)


@router.put("/change-password", response_model=dict)
def change_password(
    payload: ChangePasswordRequest,
    user: sqlite3.Row = Depends(get_current_user),
    db: sqlite3.Connection = Depends(get_db),
):
    if not verify_password(payload.currentPassword, user["passwordHash"]):
        raise HTTPException(status_code=400, detail="Current password is incorrect.")
    if len(payload.newPassword) < 4:
        raise HTTPException(status_code=400, detail="Password must be at least 4 characters.")

    db.execute(
        "UPDATE users SET passwordHash = ? WHERE id = ?",
        (hash_password(payload.newPassword), user["id"]),
    )
    write_audit_log(db, user["fullName"], user["role"], "PASSWORD_CHANGE", "Password changed successfully.")
    db.commit()

    return {"message": "Password changed successfully."}
