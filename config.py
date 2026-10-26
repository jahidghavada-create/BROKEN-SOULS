import os
from pathlib import Path
import secrets

from dotenv import load_dotenv

load_dotenv()

# Keep a localhost default for local development only. Vercel must be configured
# with a hosted DATABASE_URL instead of silently trying 127.0.0.1.
_local_database_url = "mysql://root:password@127.0.0.1:3306/broken_souls"
_database_default = "" if os.getenv("VERCEL") == "1" else _local_database_url


class Config:
    SECRET_KEY = os.getenv("FLASK_SECRET_KEY") or secrets.token_hex(32)
    DATABASE_URL = os.getenv("DATABASE_URL", _database_default).strip()
    TIMEZONE = os.getenv("TIMEZONE", "Asia/Kolkata")
    YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY", "")
    MAX_CONTENT_LENGTH = 2 * 1024 * 1024
    WTF_CSRF_TIME_LIMIT = 3600
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = os.getenv("SESSION_COOKIE_SECURE", "0") == "1"
    SQLITE_PATH = os.getenv(
        "SQLITE_PATH", str(Path(__file__).parent / "instance" / "test.sqlite3")
    )
