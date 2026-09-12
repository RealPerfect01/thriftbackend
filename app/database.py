"""
SQLite access layer.

Uses the Python standard library's `sqlite3` module directly (no ORM) so the
schema below maps one-to-one with the tables you can inspect with any SQLite
browser. A new connection is opened per request (see get_db in deps.py) which
keeps things simple and avoids cross-thread sqlite3 issues.
"""
import sqlite3
import time
from contextlib import closing

from app.config import DATABASE_PATH
from app.security import hash_password


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fullName TEXT NOT NULL,
    phoneNumber TEXT NOT NULL UNIQUE,
    email TEXT NOT NULL UNIQUE,
    homeAddress TEXT NOT NULL,
    idNumber TEXT NOT NULL,
    thriftPlan TEXT NOT NULL,
    passwordHash TEXT NOT NULL,
    role TEXT NOT NULL CHECK(role IN ('ADMIN','CUSTOMER')),
    status TEXT NOT NULL CHECK(status IN ('APPROVED','PENDING','REJECTED','SUSPENDED','DEACTIVATED')),
    savingsBalance REAL NOT NULL DEFAULT 0,
    targetAmount REAL NOT NULL DEFAULT 100000,
    createdAt INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    reference TEXT NOT NULL UNIQUE,
    userId INTEGER NOT NULL REFERENCES users(id),
    customerName TEXT NOT NULL,
    amount REAL NOT NULL,
    plan TEXT NOT NULL,
    paymentMethod TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('SUCCESS','PENDING','FAILED')),
    channelReference TEXT,
    timestamp INTEGER NOT NULL,
    notes TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS audit_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    actorName TEXT NOT NULL,
    actorRole TEXT NOT NULL,
    action TEXT NOT NULL,
    details TEXT NOT NULL,
    timestamp INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    recipientRole TEXT NOT NULL CHECK(recipientRole IN ('ALL','ADMIN','CUSTOMER')),
    userId INTEGER REFERENCES users(id),
    title TEXT NOT NULL,
    message TEXT NOT NULL,
    isRead INTEGER NOT NULL DEFAULT 0,
    timestamp INTEGER NOT NULL
);
"""


def init_db() -> None:
    """Create tables if they don't exist yet, then seed demo data once."""
    with closing(get_connection()) as conn:
        conn.executescript(SCHEMA)
        conn.commit()
        _seed_if_empty(conn)


def _seed_if_empty(conn: sqlite3.Connection) -> None:
    count = conn.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"]
    if count > 0:
        return

    now = int(time.time() * 1000)
    one_day = 86_400_000

    def insert_user(**kwargs) -> int:
        kwargs["passwordHash"] = hash_password(kwargs.pop("password"))
        cols = ", ".join(kwargs.keys())
        placeholders = ", ".join("?" for _ in kwargs)
        cur = conn.execute(
            f"INSERT INTO users ({cols}) VALUES ({placeholders})",
            tuple(kwargs.values()),
        )
        return cur.lastrowid

    def insert_transaction(**kwargs) -> int:
        cols = ", ".join(kwargs.keys())
        placeholders = ", ".join("?" for _ in kwargs)
        cur = conn.execute(
            f"INSERT INTO transactions ({cols}) VALUES ({placeholders})",
            tuple(kwargs.values()),
        )
        return cur.lastrowid

    def insert_log(**kwargs) -> None:
        cols = ", ".join(kwargs.keys())
        placeholders = ", ".join("?" for _ in kwargs)
        conn.execute(
            f"INSERT INTO audit_logs ({cols}) VALUES ({placeholders})",
            tuple(kwargs.values()),
        )

    def insert_notification(**kwargs) -> None:
        kwargs.setdefault("userId", None)
        kwargs.setdefault("isRead", 0)
        cols = ", ".join(kwargs.keys())
        placeholders = ", ".join("?" for _ in kwargs)
        conn.execute(
            f"INSERT INTO notifications ({cols}) VALUES ({placeholders})",
            tuple(kwargs.values()),
        )

    # 1. Admin
    admin_id = insert_user(
        fullName="Mr. Olumide Adeleke",
        phoneNumber="08012340000",
        email="admin@tumton.com",
        homeAddress="Tumton Towers, 14 Marina St, Lagos",
        idNumber="STAFF-TFH-001",
        thriftPlan="Staff Admin",
        password="admin123",
        role="ADMIN",
        status="APPROVED",
        savingsBalance=0.0,
        targetAmount=100000.0,
        createdAt=now - (30 * one_day),
    )

    # 2. Bisi - Daily contributor
    bisi_id = insert_user(
        fullName="Bisi Adebayo",
        phoneNumber="08031234567",
        email="bisi@tumton.com",
        homeAddress="12 Allen Avenue, Ikeja, Lagos",
        idNumber="NIN-839201948",
        thriftPlan="Daily",
        password="user123",
        role="CUSTOMER",
        status="APPROVED",
        savingsBalance=45000.0,
        targetAmount=150000.0,
        createdAt=now - (15 * one_day),
    )

    # 3. Emeka - Weekly contributor
    emeka_id = insert_user(
        fullName="Emeka Okafor",
        phoneNumber="08059876543",
        email="emeka@tumton.com",
        homeAddress="8 Awolowo Way, Bodija, Ibadan",
        idNumber="NIN-492018471",
        thriftPlan="Weekly",
        password="user123",
        role="CUSTOMER",
        status="APPROVED",
        savingsBalance=120000.0,
        targetAmount=300000.0,
        createdAt=now - (25 * one_day),
    )

    # 4. Fatima - Pending approval
    insert_user(
        fullName="Fatima Aliyu",
        phoneNumber="08123344556",
        email="fatima@tumton.com",
        homeAddress="45 Bompai Road, Kano",
        idNumber="NIN-771920482",
        thriftPlan="Monthly",
        password="user123",
        role="CUSTOMER",
        status="PENDING",
        savingsBalance=0.0,
        targetAmount=500000.0,
        createdAt=now - (2 * one_day),
    )

    # Transactions for Bisi
    insert_transaction(
        reference="THRF-2026-08140",
        userId=bisi_id,
        customerName="Bisi Adebayo",
        amount=15000.0,
        plan="Daily",
        paymentMethod="Debit Card",
        status="SUCCESS",
        channelReference="PAY-GTB-89218",
        timestamp=now - (1 * one_day),
        notes="Daily Thrift Contribution (Days 28-30)",
    )
    insert_transaction(
        reference="THRF-2026-07921",
        userId=bisi_id,
        customerName="Bisi Adebayo",
        amount=30000.0,
        plan="Daily",
        paymentMethod="Bank Transfer",
        status="SUCCESS",
        channelReference="TRF-ZEN-39102",
        timestamp=now - (5 * one_day),
        notes="Thrift cycle installment",
    )

    # Transactions for Emeka
    insert_transaction(
        reference="THRF-2026-07850",
        userId=emeka_id,
        customerName="Emeka Okafor",
        amount=40000.0,
        plan="Weekly",
        paymentMethod="Debit Card",
        status="SUCCESS",
        channelReference="PAY-ACC-99201",
        timestamp=now - (3 * one_day),
        notes="Week 8 Thrift Contribution",
    )
    insert_transaction(
        reference="THRF-2026-07412",
        userId=emeka_id,
        customerName="Emeka Okafor",
        amount=80000.0,
        plan="Weekly",
        paymentMethod="Bank Transfer",
        status="SUCCESS",
        channelReference="TRF-FBN-11928",
        timestamp=now - (12 * one_day),
        notes="Weeks 6-7 Thrift Contribution",
    )

    # Audit logs
    insert_log(
        actorName="System",
        actorRole="SYSTEM",
        action="SYSTEM_INITIALIZE",
        details="Tumton Financial Home Thrift Collection API started.",
        timestamp=now - (30 * one_day),
    )
    insert_log(
        actorName="Mr. Olumide Adeleke",
        actorRole="ADMIN",
        action="APPROVE_CUSTOMER",
        details="Approved KYC & Thrift registration for customer Bisi Adebayo (Plan: Daily)",
        timestamp=now - (14 * one_day),
    )
    insert_log(
        actorName="Mr. Olumide Adeleke",
        actorRole="ADMIN",
        action="APPROVE_CUSTOMER",
        details="Approved KYC & Thrift registration for customer Emeka Okafor (Plan: Weekly)",
        timestamp=now - (24 * one_day),
    )
    insert_log(
        actorName="Fatima Aliyu",
        actorRole="CUSTOMER",
        action="REGISTER",
        details="Customer submitted self-service registration. Pending Admin approval.",
        timestamp=now - (2 * one_day),
    )

    # Notifications
    insert_notification(
        recipientRole="ADMIN",
        title="New Registration Awaiting Approval",
        message="Fatima Aliyu registered for Monthly Thrift Plan. Review KYC and approve.",
        timestamp=now - (2 * one_day),
    )
    insert_notification(
        recipientRole="CUSTOMER",
        userId=bisi_id,
        title="Contribution Confirmed",
        message="Your contribution of \u20a615,000 has been recorded successfully. Ref: THRF-2026-08140.",
        timestamp=now - (1 * one_day),
    )
    insert_notification(
        recipientRole="CUSTOMER",
        userId=bisi_id,
        title="Welcome to Tumton Thrift!",
        message="Your account has been approved by Tumton Financial Home. You may now make thrift contributions.",
        timestamp=now - (14 * one_day),
    )

    conn.commit()
