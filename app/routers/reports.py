import csv
import io
import sqlite3
import time

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse

from app.deps import get_db, require_admin
from app.schemas import ReportSummary

router = APIRouter(prefix="/api/reports", tags=["reports"])

_RANGE_SECONDS = {
    "daily": 1 * 86_400,
    "weekly": 7 * 86_400,
    "monthly": 30 * 86_400,
}


def _resolve_range(range_name: str, start: int | None, end: int | None) -> tuple[int, int]:
    if start is not None and end is not None:
        return start, end
    now = int(time.time() * 1000)
    window_seconds = _RANGE_SECONDS.get(range_name, _RANGE_SECONDS["monthly"])
    return now - window_seconds * 1000, now


@router.get("/summary", response_model=ReportSummary)
def get_summary(
    range: str = Query(default="monthly", pattern="^(daily|weekly|monthly|custom)$"),
    start: int | None = Query(default=None, description="Start timestamp in ms (for range=custom)"),
    end: int | None = Query(default=None, description="End timestamp in ms (for range=custom)"),
    admin: sqlite3.Row = Depends(require_admin),
    db: sqlite3.Connection = Depends(get_db),
):
    start_ts, end_ts = _resolve_range(range, start, end)

    tx_row = db.execute(
        "SELECT COALESCE(SUM(amount), 0) AS total, COUNT(*) AS cnt "
        "FROM transactions WHERE status = 'SUCCESS' AND timestamp BETWEEN ? AND ?",
        (start_ts, end_ts),
    ).fetchone()

    active_savers = db.execute(
        "SELECT COUNT(DISTINCT userId) AS c FROM transactions "
        "WHERE status = 'SUCCESS' AND timestamp BETWEEN ? AND ?",
        (start_ts, end_ts),
    ).fetchone()["c"]

    # Defaulters: approved customers who made no successful contribution in the window.
    defaulters = db.execute(
        "SELECT COUNT(*) AS c FROM users "
        "WHERE role = 'CUSTOMER' AND status = 'APPROVED' AND id NOT IN ("
        "  SELECT DISTINCT userId FROM transactions "
        "  WHERE status = 'SUCCESS' AND timestamp BETWEEN ? AND ?"
        ")",
        (start_ts, end_ts),
    ).fetchone()["c"]

    return ReportSummary(
        range=range,
        startTimestamp=start_ts,
        endTimestamp=end_ts,
        totalCollected=tx_row["total"],
        numberOfTransactions=tx_row["cnt"],
        activeSavers=active_savers,
        defaulters=defaulters,
    )


@router.get("/export")
def export_transactions_csv(
    range: str = Query(default="monthly", pattern="^(daily|weekly|monthly|custom)$"),
    start: int | None = Query(default=None),
    end: int | None = Query(default=None),
    admin: sqlite3.Row = Depends(require_admin),
    db: sqlite3.Connection = Depends(get_db),
):
    start_ts, end_ts = _resolve_range(range, start, end)
    rows = db.execute(
        "SELECT reference, customerName, amount, plan, paymentMethod, status, timestamp, notes "
        "FROM transactions WHERE timestamp BETWEEN ? AND ? ORDER BY timestamp DESC",
        (start_ts, end_ts),
    ).fetchall()

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["Reference", "Customer", "Amount", "Plan", "Payment Method", "Status", "Timestamp", "Notes"])
    for r in rows:
        writer.writerow(
            [r["reference"], r["customerName"], r["amount"], r["plan"], r["paymentMethod"],
             r["status"], r["timestamp"], r["notes"]]
        )
    buffer.seek(0)

    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=tumton_report_{range}.csv"},
    )
