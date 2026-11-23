"""Rolling hourly per-IP and daily global DeepSeek quota limiter."""
import os
import time
from datetime import datetime, timezone

from fastapi import Request

from .state_db import connect_state_db, write_lock

HOUR_SECONDS = 3600.0


def hourly_limit() -> int:
    try:
        return max(1, int(os.environ.get("AGENT_LLM_HOURLY_LIMIT_PER_IP", "20")))
    except ValueError:
        return 20


def daily_global_limit() -> int:
    try:
        return max(1, int(os.environ.get("AGENT_LLM_DAILY_GLOBAL_LIMIT", "500")))
    except ValueError:
        return 500


def trust_proxy_headers() -> bool:
    return os.environ.get("AGENT_TRUST_PROXY_HEADERS", "1").strip() == "1"


def extract_client_ip(request: Request | None) -> str:
    if request is None:
        return "local"
    if trust_proxy_headers():
        x_real = (request.headers.get("x-real-ip") or "").strip()
        if x_real:
            return x_real[:64]
        xff = (request.headers.get("x-forwarded-for") or "").strip()
        if xff:
            return xff.split(",")[0].strip()[:64] or "unknown"
    if request.client and request.client.host:
        return str(request.client.host)[:64]
    return "unknown"


def _utc_day_key(now: float) -> str:
    return datetime.fromtimestamp(now, tz=timezone.utc).strftime("%Y-%m-%d")


def check_llm_quota(client_ip: str) -> dict:
    """Return current remaining hourly (per-IP) and daily (global) quota."""
    now = time.time()
    h_lim = hourly_limit()
    d_lim = daily_global_limit()
    hour_ago = now - HOUR_SECONDS
    day_key = _utc_day_key(now)
    ip = (client_ip or "unknown")[:64]

    con = connect_state_db()
    try:
        row_h = con.execute(
            "SELECT COUNT(*), MIN(created_at) FROM llm_rate_events "
            "WHERE client_ip = ? AND created_at >= ?",
            (ip, hour_ago),
        ).fetchone()
        used_hourly = int(row_h[0] or 0)
        oldest_hourly = float(row_h[1]) if row_h[1] is not None else now
        used_daily = int(
            con.execute(
                "SELECT COUNT(*) FROM llm_rate_events WHERE day_key = ?",
                (day_key,),
            ).fetchone()[0]
            or 0
        )
    finally:
        con.close()

    rem_hourly = max(0, h_lim - used_hourly)
    rem_daily = max(0, d_lim - used_daily)
    reset_in = max(0, int((oldest_hourly + HOUR_SECONDS) - now)) if used_hourly >= h_lim else 0

    reason = None
    allowed = True
    if used_hourly >= h_lim:
        allowed = False
        reason = (
            f"Hourly DeepSeek limit reached ({used_hourly}/{h_lim} calls/hr for this IP; "
            f"resets in ~{max(1, reset_in // 60)} min). Running deterministic multi-step pipeline."
        )
    elif used_daily >= d_lim:
        allowed = False
        reason = (
            f"Daily global DeepSeek cap reached ({used_daily}/{d_lim} calls today). "
            "Running deterministic multi-step pipeline."
        )

    return {
        "allowed": allowed,
        "reason": reason,
        "used_hourly": used_hourly,
        "remaining_hourly": rem_hourly,
        "hourly_limit": h_lim,
        "used_daily": used_daily,
        "remaining_daily": rem_daily,
        "daily_limit": d_lim,
        "reset_in_sec": reset_in,
    }


def record_llm_usage(client_ip: str) -> None:
    """Record one DeepSeek ReAct invocation and prune events older than 48 hours."""
    now = time.time()
    ip = (client_ip or "unknown")[:64]
    day_key = _utc_day_key(now)
    cutoff = now - 48.0 * HOUR_SECONDS
    with write_lock():
        con = connect_state_db()
        try:
            con.execute(
                "INSERT INTO llm_rate_events (client_ip, day_key, created_at) VALUES (?, ?, ?)",
                (ip, day_key, now),
            )
            con.execute("DELETE FROM llm_rate_events WHERE created_at < ?", (cutoff,))
            con.commit()
        finally:
            con.close()
