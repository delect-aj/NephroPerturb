"""Thread-safe SQLite persistence for literature cache, sessions, and LLM rate limits.

Stored under NEPHRO_STATE_DIR (default: <repo>/var/agent_state.db) so runtime writes
never touch read-only store/ or store_lite/ bundles.
"""
import os
import sqlite3
import tempfile
import threading
import time
from pathlib import Path

_INIT_LOCK = threading.Lock()
_WRITE_LOCK = threading.Lock()
_INITIALIZED_PATHS: set[str] = set()


def get_state_dir() -> Path:
    env = os.environ.get("NEPHRO_STATE_DIR", "").strip()
    if env:
        base = Path(env)
    else:
        base = Path(__file__).resolve().parents[2] / "var"
    try:
        base.mkdir(parents=True, exist_ok=True)
        return base
    except OSError:
        fallback = Path(tempfile.gettempdir()) / "nephroperturb_var"
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback


def get_db_path() -> Path:
    return get_state_dir() / "agent_state.db"


def _init_schema(con: sqlite3.Connection) -> None:
    con.execute("PRAGMA journal_mode=WAL;")
    con.execute("PRAGMA synchronous=NORMAL;")
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS literature_cache (
            cache_key TEXT PRIMARY KEY,
            source TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            created_at REAL NOT NULL
        )
        """
    )
    con.execute(
        "CREATE INDEX IF NOT EXISTS idx_lit_created ON literature_cache(created_at)"
    )
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS agent_sessions (
            session_id TEXT PRIMARY KEY,
            state_json TEXT NOT NULL,
            updated_at REAL NOT NULL
        )
        """
    )
    con.execute(
        "CREATE INDEX IF NOT EXISTS idx_sess_updated ON agent_sessions(updated_at)"
    )
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS llm_rate_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            client_ip TEXT NOT NULL,
            day_key TEXT NOT NULL,
            created_at REAL NOT NULL
        )
        """
    )
    con.execute(
        "CREATE INDEX IF NOT EXISTS idx_rate_ip_ts ON llm_rate_events(client_ip, created_at)"
    )
    con.execute(
        "CREATE INDEX IF NOT EXISTS idx_rate_day ON llm_rate_events(day_key)"
    )
    con.commit()


def connect_state_db() -> sqlite3.Connection:
    db_path = get_db_path()
    key = str(db_path.resolve())
    con = sqlite3.connect(str(db_path), timeout=15.0, check_same_thread=False)
    if key not in _INITIALIZED_PATHS:
        with _INIT_LOCK:
            if key not in _INITIALIZED_PATHS:
                _init_schema(con)
                _INITIALIZED_PATHS.add(key)
    return con


def write_lock() -> threading.Lock:
    return _WRITE_LOCK


def prune_table_if_needed(
    con: sqlite3.Connection, table: str, ts_col: str, max_age_sec: float, max_rows: int
) -> None:
    """Keep runtime SQLite footprint bounded (< few MB) on small servers."""
    cutoff = time.time() - max_age_sec
    con.execute(f"DELETE FROM {table} WHERE {ts_col} < ?", (cutoff,))
    count = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    if count > max_rows:
        excess = count - max_rows
        con.execute(
            f"DELETE FROM {table} WHERE rowid IN "
            f"(SELECT rowid FROM {table} ORDER BY {ts_col} ASC LIMIT ?)",
            (excess,),
        )
