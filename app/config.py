"""
Central configuration, loaded from environment variables (with sane defaults
for local development). Copy .env.example to .env and edit it, or just export
these as real environment variables before starting the server.
"""
import os

# Load a .env file into os.environ if python-dotenv style vars are present.
# We avoid adding python-dotenv as a hard dependency; this tiny loader covers
# the common case (KEY=VALUE per line, # comments, blank lines).
def _load_dotenv(path: str = ".env") -> None:
    if not os.path.exists(path):
        return
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip()
            if key and key not in os.environ:
                os.environ[key] = value


_load_dotenv()

JWT_SECRET = os.environ.get("JWT_SECRET", "tumton-super-secret-change-me")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_MINUTES = int(os.environ.get("JWT_EXPIRE_MINUTES", "60"))

DATABASE_PATH = os.environ.get("DATABASE_PATH", "tumton.db")

PAYSTACK_SECRET_KEY = os.environ.get(
    "PAYSTACK_SECRET_KEY", "sk_test_e7b2389104081974bbdf90184719041289190284"
)
PAYSTACK_PUBLIC_KEY = os.environ.get(
    "PAYSTACK_PUBLIC_KEY", "pk_test_d3a8e7e1f4095818987b77bfb084920401827492"
)
FLUTTERWAVE_SECRET_KEY = os.environ.get(
    "FLUTTERWAVE_SECRET_KEY", "FLWSECK_TEST-481902849182390-X"
)
FLUTTERWAVE_PUBLIC_KEY = os.environ.get(
    "FLUTTERWAVE_PUBLIC_KEY", "FLWPUBK_TEST-938217048129038-X"
)
