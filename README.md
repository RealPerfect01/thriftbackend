# Tumton Thrift API

A FastAPI + SQLite backend for the Tumton Financial Home mobile thrift
collection app. Every endpoint here maps 1:1 to a function that used to live
in `ThriftRepository.kt` on the Android side — see
`tumton_api_integration_plan.md` for the full mapping table.

Requires **Python 3.10+** (uses modern `X | Y` type hints).

---

## 1. Setup

```bash
cd tumton-backend
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

Optionally copy `.env.example` to `.env` and edit values (JWT secret, Paystack
test keys, etc.) — sensible defaults are already baked in so this step is
optional for a demo.

```bash
cp .env.example .env
```

## 2. Run

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

- The SQLite database file `tumton.db` is created automatically on first run,
  in the project root, seeded with the same demo accounts that were in the
  Android app's `AppDatabase.kt`.
- Interactive API docs (Swagger UI): **http://localhost:8000/docs**
- Alternative docs (ReDoc): **http://localhost:8000/redoc**

To let a phone/emulator on the same network reach it, use your machine's LAN
IP instead of `localhost` (e.g. `http://192.168.1.50:8000`). Android
emulators specifically should use `http://10.0.2.2:8000` to reach your
host machine.

## 3. Demo Accounts (seeded automatically)

| Role | Identifier | Password |
|---|---|---|
| Admin | `admin@tumton.com` or `08012340000` | `admin123` |
| Customer (approved) | `bisi@tumton.com` or `08031234567` | `user123` |
| Customer (approved) | `emeka@tumton.com` or `08059876543` | `user123` |
| Customer (pending approval) | `fatima@tumton.com` or `08123344556` | `user123` |

## 4. Quick Test with curl

```bash
# Login as admin
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"identifier": "admin@tumton.com", "password": "admin123"}'

# Copy the accessToken from the response, then:
TOKEN="paste_token_here"

# List all customers
curl http://localhost:8000/api/customers -H "Authorization: Bearer $TOKEN"

# Approve Fatima's pending account (find her id from the customers list first)
curl -X PUT http://localhost:8000/api/customers/4/approve -H "Authorization: Bearer $TOKEN"

# Log in as a customer and make a contribution
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"identifier": "bisi@tumton.com", "password": "user123"}'

CUSTOMER_TOKEN="paste_token_here"

curl -X POST http://localhost:8000/api/transactions/contribute \
  -H "Authorization: Bearer $CUSTOMER_TOKEN" -H "Content-Type: application/json" \
  -d '{"amount": 5000, "plan": "Daily", "paymentMethod": "Debit Card", "notes": "Test contribution"}'
```

Every write here is easiest to explore visually via the Swagger UI at
`/docs` — you can click "Authorize", paste the token, and try every endpoint
from the browser.

## 5. Project Structure

```
tumton-backend/
├── requirements.txt
├── .env.example
├── README.md
├── tumton.db                  ← created automatically on first run
└── app/
    ├── main.py                 FastAPI app, CORS, router registration
    ├── config.py                Env var loading
    ├── database.py               SQLite schema + seed data
    ├── security.py               bcrypt password hashing + JWT
    ├── deps.py                   get_db / get_current_user / require_admin
    ├── helpers.py                 audit log + notification + row-mapping helpers
    ├── schemas.py                 Pydantic request/response models
    └── routers/
        ├── auth.py                login, register, forgot/reset password
        ├── me.py                   self-service profile + change password
        ├── customers.py            admin: CRUD, approve/reject/suspend/etc.
        ├── transactions.py         list, contribute, failed contribution
        ├── notifications.py        admin + customer notifications
        ├── audit.py                 read-only audit log
        ├── reports.py                summary aggregates + CSV export
        └── payments.py               Paystack/Flutterwave test-mode initialize/verify
```

## 6. Security Notes

- Passwords are hashed with **bcrypt** before storage — the original Android
  app stored plaintext passwords in Room; this backend never does.
- The Paystack/Flutterwave **secret keys now live only on the server**
  (`app/config.py` / `.env`) — the Android app never sees them, unlike the
  original `PaymentGatewayService.kt`, which hardcoded the secret key inside
  the APK.
- JWT access tokens expire after 60 minutes by default (`JWT_EXPIRE_MINUTES`
  in `.env`).

## 7. What's Deliberately Simplified for a School Project

- **Password-reset OTPs** are kept in an in-memory dictionary (`app/routers/auth.py`),
  not a database table — they reset if the server restarts. Fine for a demo;
  move to a `password_resets` table for production.
- **PDF export** isn't implemented for reports, only CSV
  (`GET /api/reports/export`) — CSV opens fine in Excel and needs no extra
  dependency. Add `reportlab` or `fpdf2` later if a PDF is specifically required.
- **CORS is wide open** (`allow_origins=["*"]`) for easy local testing —
  restrict this before any real deployment.

## 8. Next Step

The Android app's `ThriftRepository.kt` needs a Retrofit-based `ApiService`
added alongside the existing Room database (used as an offline cache) — see
`tumton_api_integration_plan.md`, Section 6, Option A for the exact plan.
