import os
from pathlib import Path
import secrets

from dotenv import load_dotenv

load_dotenv()


class Config:
    SECRET_KEY = os.getenv("FLASK_SECRET_KEY") or secrets.token_hex(32)
    DATABASE_URL = os.getenv(
        "DATABASE_URL", "mysql://root:password@127.0.0.1:3306/broken_souls"
    )
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
