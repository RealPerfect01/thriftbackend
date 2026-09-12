"""
Paystack / Flutterwave integration, TEST MODE ONLY.

This mirrors the logic that used to live in PaymentGatewayService.kt on the
Android side, with one important change: the secret keys now live on the
server only. The Android app never sees PAYSTACK_SECRET_KEY /
FLUTTERWAVE_SECRET_KEY anymore — it just calls these two endpoints.

Behavior:
1. /initialize creates a payment session/reference (real Paystack sandbox
   call if reachable, otherwise a local "offline defense" simulation so a
   demo still works without internet).
2. /verify evaluates the outcome. If the card number matches one of the
   PRESET_TEST_CARDS below, that card's scripted outcome is used (handy for
   demonstrating a declined/failed payment on purpose). Otherwise it treats
   the payment as approved in test mode. On success, it writes the
   transaction the same way POST /api/transactions/contribute does.
"""
import json
import sqlite3
import urllib.request
import uuid
from urllib.error import URLError

from fastapi import APIRouter, Depends

from app.config import PAYSTACK_SECRET_KEY
from app.deps import get_current_user, get_db
from app.helpers import create_notification, new_reference, now_ms, transaction_row_to_dict, write_audit_log
from app.schemas import (
    PaymentInitRequest,
    PaymentInitResponse,
    PaymentVerifyRequest,
    PaymentVerifyResponse,
)

router = APIRouter(prefix="/api/payments", tags=["payments"])

PRESET_TEST_CARDS = {
    "4084084084084081": {"outcome": "SUCCESS", "reason": "Approved by issuer switch"},
    "4084084084084082": {
        "outcome": "INSUFFICIENT_FUNDS",
        "reason": "Declined: Insufficient funds in contributor account",
    },
    "4084084084084083": {"outcome": "EXPIRED_CARD", "reason": "Declined: Card is expired"},
    "4084084084084084": {
        "outcome": "BANK_DECLINED",
        "reason": "Declined: Restricted card / Contact issuer bank",
    },
}


@router.post("/initialize", response_model=PaymentInitResponse)
def initialize_transaction(
    payload: PaymentInitRequest,
    user: sqlite3.Row = Depends(get_current_user),
):
    prefix = "pstk_ref" if payload.gateway.lower() == "paystack" else "flw_ref"
    reference = f"{prefix}_{uuid.uuid4().hex[:14]}"

    if payload.gateway.lower() == "paystack":
        try:
            req_body = json.dumps(
                {
                    "email": user["email"],
                    "amount": int(payload.amount * 100),  # kobo
                    "reference": reference,
                    "metadata": {"thrift_plan": payload.plan, "application": "Tumton Financial Home"},
                }
            ).encode("utf-8")
            req = urllib.request.Request(
                "https://api.paystack.co/transaction/initialize",
                data=req_body,
                method="POST",
                headers={
                    "Authorization": f"Bearer {PAYSTACK_SECRET_KEY}",
                    "Content-Type": "application/json",
                },
            )
            with urllib.request.urlopen(req, timeout=4) as resp:
                if resp.status in (200, 201):
                    body = json.loads(resp.read().decode("utf-8"))
                    data = body.get("data", {})
                    return PaymentInitResponse(
                        isSuccess=True,
                        reference=data.get("reference", reference),
                        accessCode=data.get("access_code", f"ACC_{reference[-6:]}"),
                        authorizationUrl=data.get("authorization_url", ""),
                        message="Paystack Test Session Initialized",
                    )
        except (URLError, TimeoutError, OSError, ValueError):
            pass  # fall through to offline simulation below

    # Offline / sandbox fallback — used automatically if there's no internet
    # access (e.g. during a project defense) or for Flutterwave.
    return PaymentInitResponse(
        isSuccess=True,
        reference=reference,
        accessCode=f"AUTH_{uuid.uuid4().hex[:8].upper()}",
        authorizationUrl=f"https://checkout.paystack.com/test_{reference}",
        message="Initialized in Test Sandbox",
    )


@router.post("/verify", response_model=PaymentVerifyResponse)
def verify_transaction(
    payload: PaymentVerifyRequest,
    reference: str,
    user: sqlite3.Row = Depends(get_current_user),
    db: sqlite3.Connection = Depends(get_db),
):
    clean_card = payload.cardNumber.replace(" ", "")
    matched = PRESET_TEST_CARDS.get(clean_card)

    if matched and matched["outcome"] != "SUCCESS":
        return PaymentVerifyResponse(
            isSuccess=False,
            reference=reference,
            amount=payload.amount,
            gatewayResponse=matched["reason"],
            paymentMethod=payload.paymentMethod,
            channelReference=f"DECLINED-{reference[-6:]}",
            transaction=None,
        )

    # Approved (either a genuinely successful test card, or test-mode default).
    channel_reference = f"PSTK-AUTH-{uuid.uuid4().hex[:6].upper()}"
    tx_reference = new_reference()
    timestamp = now_ms()

    db.execute(
        "INSERT INTO transactions "
        "(reference, userId, customerName, amount, plan, paymentMethod, status, "
        " channelReference, timestamp, notes) "
        "VALUES (?, ?, ?, ?, ?, ?, 'SUCCESS', ?, ?, ?)",
        (
            tx_reference, user["id"], user["fullName"], payload.amount, payload.plan,
            payload.paymentMethod, channel_reference, timestamp,
            f"Paid via {payload.gateway} (test mode). Gateway ref: {reference}",
        ),
    )
    new_balance = user["savingsBalance"] + payload.amount
    db.execute("UPDATE users SET savingsBalance = ? WHERE id = ?", (new_balance, user["id"]))

    write_audit_log(
        db, user["fullName"], "CUSTOMER", "CONTRIBUTION_MADE",
        f"Thrift contribution of NGN {payload.amount:,.2f} paid via {payload.paymentMethod} "
        f"({payload.gateway} test mode). Ref: {tx_reference}",
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

    tx_row = db.execute("SELECT * FROM transactions WHERE reference = ?", (tx_reference,)).fetchone()

    return PaymentVerifyResponse(
        isSuccess=True,
        reference=reference,
        amount=payload.amount,
        gatewayResponse="Approved (Test Mode Verified)",
        paymentMethod=payload.paymentMethod,
        channelReference=channel_reference,
        transaction=transaction_row_to_dict(tx_row),
    )
