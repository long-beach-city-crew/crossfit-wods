"""SQLite storage for users and per-user workout progress."""

import sqlite3
from collections.abc import Iterator
from pathlib import Path

INSTANCE_DIR = Path(__file__).resolve().parent.parent / "instance"
DB_PATH = INSTANCE_DIR / "app.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS progress (
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    wod_id TEXT NOT NULL,
    done_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, wod_id)
);
"""


def connect() -> sqlite3.Connection:
    # Requests run in FastAPI's threadpool; each connection is used by one request only.
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with connect() as conn:
        conn.executescript(SCHEMA)


def get_db() -> Iterator[sqlite3.Connection]:
    conn = connect()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def create_user(conn: sqlite3.Connection, email: str, password_hash: str) -> int | None:
    """Return the new user's id, or None if the email is taken."""
    try:
        cur = conn.execute(
            "INSERT INTO users (email, password_hash) VALUES (?, ?)", (email, password_hash)
        )
    except sqlite3.IntegrityError:
        return None
    return cur.lastrowid


def user_by_email(conn: sqlite3.Connection, email: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()


def user_by_id(conn: sqlite3.Connection, user_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()


def done_wods(conn: sqlite3.Connection, user_id: int) -> dict[str, str]:
    """Map of wod id -> done_at timestamp for the user."""
    rows = conn.execute("SELECT wod_id, done_at FROM progress WHERE user_id = ?", (user_id,))
    return {r["wod_id"]: r["done_at"] for r in rows}


def set_done(conn: sqlite3.Connection, user_id: int, wod_id: str, done: bool) -> None:
    if done:
        conn.execute(
            "INSERT OR IGNORE INTO progress (user_id, wod_id) VALUES (?, ?)", (user_id, wod_id)
        )
    else:
        conn.execute("DELETE FROM progress WHERE user_id = ? AND wod_id = ?", (user_id, wod_id))
