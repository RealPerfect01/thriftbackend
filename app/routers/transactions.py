import sqlite3
from typing import Optional

from fastapi import APIRouter, Depends, Query

from app.deps import get_current_user, get_db, require_admin
from app.helpers import (
    create_notification,
    new_reference,
    now_ms,
    transaction_row_to_dict,
    write_audit_log,
)
from app.schemas import ContributionRequest, FailedContributionRequest, TransactionOut

router = APIRouter(prefix="/api/transactions", tags=["transactions"])


@router.get("", response_model=list[TransactionOut])
def list_all_transactions(
    status_filter: Optional[str] = Query(default=None, alias="status"),
    customer_id: Optional[int] = Query(default=None, alias="customerId"),
    admin: sqlite3.Row = Depends(require_admin),
    db: sqlite3.Connection = Depends(get_db),
):
    query = "SELECT * FROM transactions WHERE 1=1"
    params: list = []
    if status_filter:
        query += " AND status = ?"
        params.append(status_filter.upper())
    if customer_id:
        query += " AND userId = ?"
        params.append(customer_id)
    query += " ORDER BY timestamp DESC"

    rows = db.execute(query, params).fetchall()
    return [transaction_row_to_dict(r) for r in rows]


@router.get("/me", response_model=list[TransactionOut])
def list_my_transactions(
    user: sqlite3.Row = Depends(get_current_user),
    db: sqlite3.Connection = Depends(get_db),
):
    rows = db.execute(
        "SELECT * FROM transactions WHERE userId = ? ORDER BY timestamp DESC", (user["id"],)
    ).fetchall()
    return [transaction_row_to_dict(r) for r in rows]


@router.post("/contribute", response_model=TransactionOut, status_code=201)
def make_contribution(
    payload: ContributionRequest,
    user: sqlite3.Row = Depends(get_current_user),
    db: sqlite3.Connection = Depends(get_db),
):
    """
    Records a SUCCESSFUL contribution. This is called after the payment
    gateway (see /api/payments/verify) has confirmed the payment succeeded —
    it never takes card details directly.
    """
    reference = new_reference()
    timestamp = now_ms()

    db.execute(
        "INSERT INTO transactions "
        "(reference, userId, customerName, amount, plan, paymentMethod, status, "
        " channelReference, timestamp, notes) "
        "VALUES (?, ?, ?, ?, ?, ?, 'SUCCESS', ?, ?, ?)",
        (
            reference, user["id"], user["fullName"], payload.amount, payload.plan,
            payload.paymentMethod, payload.channelReference, timestamp, payload.notes,
        ),
    )

    new_balance = user["savingsBalance"] + payload.amount
    db.execute("UPDATE users SET savingsBalance = ? WHERE id = ?", (new_balance, user["id"]))

    write_audit_log(
        db, user["fullName"], "CUSTOMER", "CONTRIBUTION_MADE",
        f"Thrift contribution of NGN {payload.amount:,.2f} paid via {payload.paymentMethod}. Ref: {reference}",
    )
    create_notification(
        db, "CUSTOMER", "Contribution Received",
        f"NGN {payload.amount:,.2f} has been credited to your {payload.plan} thrift account. "
        f"New balance: NGN {new_balance:,.2f}.",
        user_id=user["id"],
    )
    create_notification(
        db, "ADMIN", "Contribution Recorded",
        f"{user['fullName']} contributed NGN {payload.amount:,.2f} ({payload.plan} plan) via {payload.paymentMethod}.",
    )
    db.commit()

    row = db.execute("SELECT * FROM transactions WHERE reference = ?", (reference,)).fetchone()
    return transaction_row_to_dict(row)


@router.post("/failed", response_model=TransactionOut, status_code=201)
def record_failed_contribution(
    payload: FailedContributionRequest,
    user: sqlite3.Row = Depends(get_current_user),
    db: sqlite3.Connection = Depends(get_db),
):
    reference = new_reference(prefix="THRF-FAIL")
    timestamp = now_ms()

    db.execute(
        "INSERT INTO transactions "
        "(reference, userId, customerName, amount, plan, paymentMethod, status, "
        " channelReference, timestamp, notes) "
        "VALUES (?, ?, ?, ?, ?, ?, 'FAILED', ?, ?, ?)",
        (
            reference, user["id"], user["fullName"], payload.amount, payload.plan,
            payload.paymentMethod, payload.channelReference, timestamp,
            f"Payment Failed: {payload.failureReason}",
        ),
    )
    # Balance is intentionally NOT updated on failure.

    write_audit_log(
        db, user["fullName"], "CUSTOMER", "PAYMENT_FAILED",
        f"Thrift contribution payment failed for NGN {payload.amount:,.2f} via {payload.paymentMethod}. "
        f"Reason: {payload.failureReason}. Ref: {reference}",
    )
    create_notification(
        db, "CUSTOMER", "Payment Failed",
        f"Your contribution of NGN {payload.amount:,.2f} could not be processed ({payload.failureReason}). "
        "Your savings balance was not charged.",
        user_id=user["id"],
    )
    db.commit()

    row = db.execute("SELECT * FROM transactions WHERE reference = ?", (reference,)).fetchone()
    return transaction_row_to_dict(row)
