"""Compact multi-turn session ledger & ordinal reference resolver."""
import json
import re
import time
import uuid

from .state_db import connect_state_db, prune_table_if_needed, write_lock

SESSION_TTL_SEC = 24 * 3600.0
MAX_SESSIONS = 300


def new_session_state(session_id: str | None = None) -> dict:
    sid = (session_id or "").strip() or uuid.uuid4().hex[:16]
    return {
        "session_id": sid,
        "active_disease": None,
        "active_case_id": None,
        "candidates": [],
        "compounds_detail": {},
        "literature_by_entity": {},
        "pmids": [],
        "ncts": [],
        "turns": [],
    }


def load_session(session_id: str | None) -> dict:
    if not session_id or not session_id.strip():
        return new_session_state()
    sid = session_id.strip()[:64]
    con = connect_state_db()
    try:
        row = con.execute(
            "SELECT state_json, updated_at FROM agent_sessions WHERE session_id = ?",
            (sid,),
        ).fetchone()
    finally:
        con.close()
    if not row:
        return new_session_state(sid)
    raw, updated_at = row
    if time.time() - float(updated_at) > SESSION_TTL_SEC:
        return new_session_state(sid)
    try:
        data = json.loads(raw)
        data.setdefault("session_id", sid)
        return data
    except Exception:
        return new_session_state(sid)


def save_session(state: dict) -> None:
    sid = state.get("session_id") or uuid.uuid4().hex[:16]
    compact = {
        "session_id": sid,
        "active_disease": state.get("active_disease"),
        "active_case_id": state.get("active_case_id"),
        "candidates": (state.get("candidates") or [])[:15],
        "compounds_detail": dict(list((state.get("compounds_detail") or {}).items())[-12:]),
        "literature_by_entity": dict(list((state.get("literature_by_entity") or {}).items())[-12:]),
        "pmids": list(dict.fromkeys(state.get("pmids") or []))[:60],
        "ncts": list(dict.fromkeys(state.get("ncts") or []))[:40],
        "turns": (state.get("turns") or [])[-6:],
    }
    raw = json.dumps(compact, ensure_ascii=False)
    with write_lock():
        con = connect_state_db()
        try:
            con.execute(
                "INSERT OR REPLACE INTO agent_sessions (session_id, state_json, updated_at) "
                "VALUES (?, ?, ?)",
                (sid, raw, time.time()),
            )
            prune_table_if_needed(con, "agent_sessions", "updated_at", SESSION_TTL_SEC, MAX_SESSIONS)
            con.commit()
        finally:
            con.close()


def delete_session(session_id: str) -> bool:
    sid = (session_id or "").strip()[:64]
    if not sid:
        return False
    with write_lock():
        con = connect_state_db()
        try:
            cur = con.execute("DELETE FROM agent_sessions WHERE session_id = ?", (sid,))
            con.commit()
            return cur.rowcount > 0
        finally:
            con.close()


_TOP_N_RE = re.compile(r"\btop\s*([2-4])\b|前\s*([2-4两三])\s*个?", re.I)
_HASH_IDX_RE = re.compile(r"#\s*([1-9]\d?)\b")
_WORD_IDX_MAP = {
    "first": 1, "1st": 1, "第1": 1, "第一": 1,
    "second": 2, "2nd": 2, "第2": 2, "第二": 2,
    "third": 3, "3rd": 3, "第3": 3, "第三": 3,
    "fourth": 4, "4th": 4, "第4": 4, "第四": 4,
}


def resolve_session_references(text: str, session_state: dict | None, find_compound_fn=None) -> list[str]:
    """Resolve ordinal (#1, #2, top 2) and explicit compound mentions from query + session."""
    cands = (session_state or {}).get("candidates") or []
    picked: list[str] = []
    seen = set()

    def add_idx(one_based: int):
        idx = one_based - 1
        if 0 <= idx < len(cands):
            c = cands[idx]
            label = c.get("pert_iname") or c.get("pert_id")
            if label and label.lower() not in seen:
                seen.add(label.lower())
                picked.append(str(label))

    # 1) "top 2" / "前两个"
    m_top = _TOP_N_RE.search(text or "")
    if m_top and cands:
        raw_n = m_top.group(1) or m_top.group(2)
        cn_map = {"两": 2, "三": 3}
        n = cn_map.get(raw_n, None) or int(raw_n)
        for i in range(1, n + 1):
            add_idx(i)

    # 2) Explicit "#1", "#2", "first", "second"
    for m in _HASH_IDX_RE.finditer(text or ""):
        add_idx(int(m.group(1)))
    low = (text or "").lower()
    for word, idx in _WORD_IDX_MAP.items():
        if re.search(rf"\b{re.escape(word)}\b" if word.isascii() else re.escape(word), low):
            add_idx(idx)

    # 3) Explicit compound tokens resolved against the DB if provided
    if find_compound_fn is not None:
        from .agent_runner import _extract_compound_candidates
        for tok in _extract_compound_candidates(text or ""):
            if tok.lower() in seen:
                continue
            hit = find_compound_fn(tok)
            if hit is not None:
                label = hit.get("pert_iname") or str(hit["pert_id"])
                if label.lower() not in seen:
                    seen.add(label.lower())
                    picked.append(str(label))

    # 4) Fallback if user referred to active drugs without explicit index
    if not picked and cands and re.search(
        r"\b(these|them|both|top candidates?|it)\b|刚才|上面|这些药", low
    ):
        for i in (1, 2):
            add_idx(i)

    return picked
