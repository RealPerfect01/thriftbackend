import sqlite3

from fastapi import APIRouter, Depends, HTTPException

from app.deps import get_db, require_admin
from app.helpers import create_notification, now_ms, user_row_to_dict, write_audit_log
from app.schemas import MessageRequest, RejectRequest, UserCreateByAdmin, UserOut, UserUpdate
from app.security import hash_password

router = APIRouter(prefix="/api/customers", tags=["customers"])


def _get_customer_or_404(db: sqlite3.Connection, customer_id: int) -> sqlite3.Row:
    row = db.execute(
        "SELECT * FROM users WHERE id = ? AND role = 'CUSTOMER'", (customer_id,)
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Customer not found.")
    return row


@router.get("", response_model=list[UserOut])
def list_customers(admin: sqlite3.Row = Depends(require_admin), db: sqlite3.Connection = Depends(get_db)):
    rows = db.execute(
        "SELECT * FROM users WHERE role = 'CUSTOMER' ORDER BY createdAt DESC"
    ).fetchall()
    return [user_row_to_dict(r) for r in rows]


@router.get("/pending", response_model=list[UserOut])
def list_pending_customers(admin: sqlite3.Row = Depends(require_admin), db: sqlite3.Connection = Depends(get_db)):
    rows = db.execute(
        "SELECT * FROM users WHERE role = 'CUSTOMER' AND status = 'PENDING' ORDER BY createdAt DESC"
    ).fetchall()
    return [user_row_to_dict(r) for r in rows]


@router.get("/{customer_id}", response_model=UserOut)
def get_customer(
    customer_id: int,
    admin: sqlite3.Row = Depends(require_admin),
    db: sqlite3.Connection = Depends(get_db),
):
    return user_row_to_dict(_get_customer_or_404(db, customer_id))


@router.post("", response_model=UserOut, status_code=201)
def create_customer(
    payload: UserCreateByAdmin,
    admin: sqlite3.Row = Depends(require_admin),
    db: sqlite3.Connection = Depends(get_db),
):
    existing = db.execute(
        "SELECT id FROM users WHERE LOWER(email) = LOWER(?) OR phoneNumber = ?",
        (payload.email, payload.phoneNumber),
    ).fetchone()
    if existing is not None:
        raise HTTPException(status_code=409, detail="A user with this email or phone already exists.")

    default_password = "Password@123"
    cur = db.execute(
        "INSERT INTO users "
        "(fullName, phoneNumber, email, homeAddress, idNumber, thriftPlan, passwordHash, "
        " role, status, savingsBalance, targetAmount, createdAt) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, 'CUSTOMER', 'APPROVED', ?, ?, ?)",
        (
            payload.fullName.strip(),
            payload.phoneNumber.strip(),
            payload.email.strip(),
            payload.homeAddress.strip(),
            payload.idNumber.strip(),
            payload.thriftPlan,
            hash_password(default_password),
            payload.initialBalance,
            payload.targetAmount,
            now_ms(),
        ),
    )
    new_id = cur.lastrowid

    write_audit_log(
        db, admin["fullName"], "ADMIN", "CREATE_CUSTOMER",
        f"Admin manually created customer account: {payload.fullName} ({payload.thriftPlan} Plan)",
    )
    create_notification(
        db, "CUSTOMER", "Welcome to Tumton Thrift!",
        f"Your thrift savings account was created by Admin. Plan: {payload.thriftPlan}. "
        f"Temporary password: {default_password}",
        user_id=new_id,
    )
    db.commit()

    return user_row_to_dict(db.execute("SELECT * FROM users WHERE id = ?", (new_id,)).fetchone())


@router.put("/{customer_id}", response_model=UserOut)
def update_customer(
    customer_id: int,
    payload: UserUpdate,
    admin: sqlite3.Row = Depends(require_admin),
    db: sqlite3.Connection = Depends(get_db),
):
    customer = _get_customer_or_404(db, customer_id)
    fields = payload.model_dump(exclude_unset=True)
    if fields:
        set_clause = ", ".join(f"{k} = ?" for k in fields)
        db.execute(
            f"UPDATE users SET {set_clause} WHERE id = ?",
            (*fields.values(), customer_id),
        )
        write_audit_log(
            db, admin["fullName"], "ADMIN", "EDIT_CUSTOMER",
            f"Admin updated account profile for: {customer['fullName']} (ID: {customer_id})",
        )
        db.commit()

    return user_row_to_dict(db.execute("SELECT * FROM users WHERE id = ?", (customer_id,)).fetchone())


def _set_status(
    db: sqlite3.Connection,
    admin: sqlite3.Row,
    customer_id: int,
    new_status: str,
    action: str,
    audit_detail: str,
    notify_title: str | None = None,
    notify_message: str | None = None,
) -> sqlite3.Row:
    customer = _get_customer_or_404(db, customer_id)
    db.execute("UPDATE users SET status = ? WHERE id = ?", (new_status, customer_id))
    write_audit_log(db, admin["fullName"], "ADMIN", action, audit_detail)
    if notify_title:
        create_notification(db, "CUSTOMER", notify_title, notify_message or "", user_id=customer_id)
    db.commit()
    return db.execute("SELECT * FROM users WHERE id = ?", (customer_id,)).fetchone()


@router.put("/{customer_id}/approve", response_model=UserOut)
def approve_customer(
    customer_id: int,
    admin: sqlite3.Row = Depends(require_admin),
    db: sqlite3.Connection = Depends(get_db),
):
    customer = _get_customer_or_404(db, customer_id)
    updated = _set_status(
        db, admin, customer_id, "APPROVED", "APPROVE_CUSTOMER",
        f"Admin approved account for customer: {customer['fullName']}",
        "Account Approved!",
        "Congratulations! Your Tumton Thrift account has been approved. You can now make contributions.",
    )
    return user_row_to_dict(updated)


@router.put("/{customer_id}/reject", response_model=UserOut)
def reject_customer(
    customer_id: int,
    payload: RejectRequest,
    admin: sqlite3.Row = Depends(require_admin),
    db: sqlite3.Connection = Depends(get_db),
):
    customer = _get_customer_or_404(db, customer_id)
    updated = _set_status(
        db, admin, customer_id, "REJECTED", "REJECT_CUSTOMER",
        f"Admin rejected customer {customer['fullName']}. Reason: {payload.reason}",
        "Registration Update",
        f"Your registration could not be approved at this time: {payload.reason}. "
        "Please contact Tumton Financial Home.",
    )
    return user_row_to_dict(updated)


@router.put("/{customer_id}/suspend", response_model=UserOut)
def suspend_customer(
    customer_id: int,
    admin: sqlite3.Row = Depends(require_admin),
    db: sqlite3.Connection = Depends(get_db),
):
    customer = _get_customer_or_404(db, customer_id)
    updated = _set_status(
        db, admin, customer_id, "SUSPENDED", "SUSPEND_CUSTOMER",
        f"Customer account suspended: {customer['fullName']}",
    )
    return user_row_to_dict(updated)


@router.put("/{customer_id}/activate", response_model=UserOut)
def activate_customer(
    customer_id: int,
    admin: sqlite3.Row = Depends(require_admin),
    db: sqlite3.Connection = Depends(get_db),
):
    customer = _get_customer_or_404(db, customer_id)
    updated = _set_status(
        db, admin, customer_id, "APPROVED", "ACTIVATE_CUSTOMER",
        f"Admin re-activated customer account: {customer['fullName']}",
        "Account Activated",
        "Your thrift account is now active and ready for contributions.",
    )
    return user_row_to_dict(updated)


@router.put("/{customer_id}/deactivate", response_model=UserOut)
def deactivate_customer(
    customer_id: int,
    admin: sqlite3.Row = Depends(require_admin),
    db: sqlite3.Connection = Depends(get_db),
):
    customer = _get_customer_or_404(db, customer_id)
    updated = _set_status(
        db, admin, customer_id, "DEACTIVATED", "DEACTIVATE_CUSTOMER",
        f"Admin deactivated customer account: {customer['fullName']}",
        "Account Deactivated",
        "Your thrift account has been temporarily deactivated by administration. "
        "Please contact Tumton Financial Home.",
    )
    return user_row_to_dict(updated)


@router.delete("/{customer_id}", response_model=dict)
def delete_customer(
    customer_id: int,
    admin: sqlite3.Row = Depends(require_admin),
    db: sqlite3.Connection = Depends(get_db),
):
    customer = _get_customer_or_404(db, customer_id)
    db.execute("DELETE FROM users WHERE id = ?", (customer_id,))
    write_audit_log(
        db, admin["fullName"], "ADMIN", "DELETE_CUSTOMER",
        f"Admin permanently deleted customer record for: {customer['fullName']}",
    )
    db.commit()
    return {"message": "Customer deleted."}


@router.post("/{customer_id}/message", response_model=dict)
def message_customer(
    customer_id: int,
    payload: MessageRequest,
    admin: sqlite3.Row = Depends(require_admin),
    db: sqlite3.Connection = Depends(get_db),
):
    customer = _get_customer_or_404(db, customer_id)
    create_notification(db, "CUSTOMER", payload.title.strip(), payload.message.strip(), user_id=customer_id)
    write_audit_log(
        db, admin["fullName"], "ADMIN", "SEND_NOTICE",
        f"Admin sent direct notice to customer {customer['fullName']}: {payload.title.strip()}",
    )
    db.commit()
    return {"message": "Message dispatched to customer."}
