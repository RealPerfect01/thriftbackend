from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import init_db
from app.routers import audit, auth, customers, me, notifications, payments, reports, transactions

app = FastAPI(
    title="Tumton Thrift API",
    description="Backend API for the Tumton Financial Home mobile thrift collection app.",
    version="1.0.0",
)

# Wide-open CORS for local development / demo. Tighten this to your app's
# actual origin before any real deployment.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup() -> None:
    init_db()


@app.get("/", tags=["health"])
def health_check():
    return {"status": "ok", "service": "Tumton Thrift API"}


app.include_router(auth.router)
app.include_router(me.router)
app.include_router(customers.router)
app.include_router(transactions.router)
app.include_router(notifications.router)
app.include_router(audit.router)
app.include_router(reports.router)
app.include_router(payments.router)
