from contextlib import contextmanager
import os
from pathlib import Path
from urllib.parse import unquote, urlparse

import pymysql
from pymysql.cursors import DictCursor


def _settings(database_url):
    parsed = urlparse(database_url)
    if parsed.scheme == "sqlite":
        path = parsed.path
        if re_drive_path(path):
            path = path[1:]
        return {"driver": "sqlite", "path": path}
    if parsed.scheme != "mysql":
        raise ValueError("DATABASE_URL must use mysql:// or sqlite://")

    host = parsed.hostname or "127.0.0.1"
    use_ssl = (
        os.getenv("DATABASE_SSL", "").strip().lower() in {"1", "true", "yes"}
        or host.endswith(".tidbcloud.com")
    )
    settings = {
        "driver": "mysql",
        "host": host,
        "port": parsed.port or 3306,
        "user": unquote(parsed.username or ""),
        "password": unquote(parsed.password or ""),
        "database": unquote(parsed.path.lstrip("/")),
        "charset": "utf8mb4",
    }
    if use_ssl:
        # TiDB Cloud requires TLS. PyMySQL verifies the server certificate using
        # the system trust store; optionally allow a CA certificate path.
        ssl_options = {"check_hostname": True}
        ca_path = os.getenv("DATABASE_SSL_CA", "").strip()
        if ca_path:
            ssl_options["ca"] = ca_path
        settings["ssl"] = ssl_options
    return settings


def re_drive_path(path):
    return len(path) >= 3 and path[0] == "/" and path[1].isalpha() and path[2] == ":"


def connect(database_url):
    settings = _settings(database_url)
    if settings["driver"] == "sqlite":
        import sqlite3

        path = settings["path"]
        if path and path != "/:memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(":memory:" if path == "/:memory:" else path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection
    return pymysql.connect(
        **{key: value for key, value in settings.items() if key != "driver"},
        cursorclass=DictCursor,
        autocommit=False,
        connect_timeout=10,
        read_timeout=20,
        write_timeout=20,
    )


def is_sqlite(database_url):
    return _settings(database_url)["driver"] == "sqlite"


def execute(connection, database_url, query, params=()):
    if is_sqlite(database_url):
        query = query.replace("%s", "?")
        return connection.execute(query, params)
    cursor = connection.cursor()
    cursor.execute(query, params)
    return cursor


def one(connection, database_url, query, params=()):
    row = execute(connection, database_url, query, params).fetchone()
    return dict(row) if row is not None and is_sqlite(database_url) else row


def all_rows(connection, database_url, query, params=()):
    rows = execute(connection, database_url, query, params).fetchall()
    return [dict(row) for row in rows] if is_sqlite(database_url) else rows


@contextmanager
def transaction(database_url):
    connection = connect(database_url)
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
