import random
import sqlite3
import time

from fastapi import APIRouter, Depends, HTTPException, status

from app.deps import get_db
from app.helpers import create_notification, now_ms, user_row_to_dict, write_audit_log
from app.schemas import (
    ForgotPasswordRequest,
    LoginRequest,
    RegisterRequest,
    ResetPasswordRequest,
    TokenResponse,
    VerifyOtpRequest,
)
from app.security import create_access_token, hash_password, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])

# In-memory OTP store for the forgot-password flow: {identifier: (otp, expires_at_epoch)}
# A project demo doesn't need this durable across server restarts; if you want
# it to survive restarts, move it into a small `password_resets` SQLite table.
_OTP_STORE: dict[str, tuple[str, float]] = {}
_OTP_TTL_SECONDS = 10 * 60


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: sqlite3.Connection = Depends(get_db)):
    identifier = payload.identifier.strip()
    user = db.execute(
        "SELECT * FROM users WHERE LOWER(email) = LOWER(?) OR phoneNumber = ?",
        (identifier, identifier),
    ).fetchone()

    if user is None or not verify_password(payload.password, user["passwordHash"]):
        write_audit_log(
            db, "Anonymous", "UNKNOWN", "LOGIN_FAILED",
            f"Failed login attempt for identifier: {identifier}",
        )
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials. Please check your details and try again.",
        )

    if user["role"] == "CUSTOMER" and user["status"] != "APPROVED":
        if user["status"] == "PENDING":
            detail = "Your registration is awaiting Admin approval."
        elif user["status"] == "SUSPENDED":
            detail = "Your account has been suspended. Please contact Tumton Financial Home support."
        else:
            detail = "Your account registration was not approved. Please contact Tumton Financial Home."
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail)

    write_audit_log(
        db, user["fullName"], user["role"], "LOGIN_SUCCESS",
        f"User successfully authenticated into {user['role']} session.",
    )
    db.commit()

    token = create_access_token(user["id"], user["role"])
    return TokenResponse(accessToken=token, user=user_row_to_dict(user))


@router.post("/register", response_model=dict)
def register(payload: RegisterRequest, db: sqlite3.Connection = Depends(get_db)):
    if payload.password != payload.confirmPassword:
        raise HTTPException(status_code=400, detail="Passwords do not match.")

    existing = db.execute(
        "SELECT id FROM users WHERE LOWER(email) = LOWER(?) OR phoneNumber = ?",
        (payload.email, payload.phoneNumber),
    ).fetchone()
    if existing is not None:
        raise HTTPException(
            status_code=409, detail="An account with this email or phone number already exists."
        )

    cur = db.execute(
        "INSERT INTO users "
        "(fullName, phoneNumber, email, homeAddress, idNumber, thriftPlan, passwordHash, "
        " role, status, savingsBalance, targetAmount, createdAt) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, 'CUSTOMER', 'PENDING', 0, 100000, ?)",
        (
            payload.fullName.strip(),
            payload.phoneNumber.strip(),
            payload.email.strip(),
            payload.homeAddress.strip(),
            payload.idNumber.strip(),
            payload.thriftPlan,
            hash_password(payload.password),
            now_ms(),
        ),
    )
    new_id = cur.lastrowid

    write_audit_log(
        db, payload.fullName, "CUSTOMER", "REGISTER",
        f"New self-service customer registration submitted ({payload.thriftPlan} Plan). "
        "Awaiting Admin verification.",
    )
    create_notification(
        db, "ADMIN", "New Registration Awaiting Approval",
        f"{payload.fullName} registered for {payload.thriftPlan} Thrift Plan. Verify KYC details.",
    )
    db.commit()

    return {"id": new_id, "status": "PENDING", "message": "Registration submitted. Awaiting Admin approval."}


@router.post("/forgot-password", response_model=dict)
def forgot_password(payload: ForgotPasswordRequest, db: sqlite3.Connection = Depends(get_db)):
    identifier = payload.identifier.strip()
    user = db.execute(
        "SELECT id FROM users WHERE LOWER(email) = LOWER(?) OR phoneNumber = ?",
        (identifier, identifier),
    ).fetchone()
    if user is None:
        # Don't reveal whether the account exists.
        return {"message": "If an account exists for this identifier, an OTP has been sent."}

    otp = f"{random.randint(0, 999999):06d}"
    _OTP_STORE[identifier.lower()] = (otp, time.time() + _OTP_TTL_SECONDS)

    # In production this would be sent via SMS/email. For the project demo,
    # it's returned directly in the response so it can be shown on-screen.
    return {"message": "OTP generated.", "otp": otp, "expiresInSeconds": _OTP_TTL_SECONDS}


@router.post("/verify-otp", response_model=dict)
def verify_otp(payload: VerifyOtpRequest):
    entry = _OTP_STORE.get(payload.identifier.strip().lower())
    if entry is None or entry[1] < time.time():
        raise HTTPException(status_code=400, detail="OTP expired or not found. Please request a new one.")
    if entry[0] != payload.otp:
        raise HTTPException(status_code=400, detail="Incorrect OTP.")
    return {"verified": True}


@router.post("/reset-password", response_model=dict)
def reset_password(payload: ResetPasswordRequest, db: sqlite3.Connection = Depends(get_db)):
    identifier = payload.identifier.strip().lower()
    entry = _OTP_STORE.get(identifier)
    if entry is None or entry[1] < time.time() or entry[0] != payload.otp:
        raise HTTPException(status_code=400, detail="Invalid or expired OTP.")

    user = db.execute(
        "SELECT * FROM users WHERE LOWER(email) = ? OR phoneNumber = ?",
        (identifier, identifier),
    ).fetchone()
    if user is None:
        raise HTTPException(status_code=404, detail="Account not found.")

    db.execute(
        "UPDATE users SET passwordHash = ? WHERE id = ?",
        (hash_password(payload.newPassword), user["id"]),
    )
    write_audit_log(
        db, user["fullName"], user["role"], "PASSWORD_RESET",
        "Password was reset successfully via OTP verification.",
    )
    db.commit()
    _OTP_STORE.pop(identifier, None)

    return {"message": "Password reset successfully."}
