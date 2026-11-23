"""Deterministic model execution policy, prompt builder, and token/loop guards."""
from dataclasses import dataclass
import json
import os


@dataclass(frozen=True)
class ModelExecutionPolicy:
    model: str
    base_url: str
    temperature: float = 0.0
    top_p: float = 1.0
    seed: int = 42
    max_steps_ceiling: int = 6
    max_tokens_step: int = 1200
    max_tokens_synthesis: int = 1200
    max_tokens_repair: int = 1000
    max_prompt_tokens: int = 15000
    max_wall_seconds: float = 45.0
    tool_digest_max_chars: int = 1250
    allow_llm_calls: bool = True

    def as_public_dict(self) -> dict:
        return {
            "model": self.model,
            "temperature": self.temperature,
            "top_p": self.top_p,
            "seed": self.seed,
            "max_steps_ceiling": self.max_steps_ceiling,
            "max_tokens_step": self.max_tokens_step,
            "max_tokens_synthesis": self.max_tokens_synthesis,
            "max_prompt_tokens": self.max_prompt_tokens,
            "max_wall_seconds": self.max_wall_seconds,
            "tool_digest_max_chars": self.tool_digest_max_chars,
        }


def get_policy() -> ModelExecutionPolicy:
    return ModelExecutionPolicy(
        model=os.environ.get("DEEPSEEK_MODEL", "deepseek-chat"),
        base_url=os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
    )


def canonical_call_key(tool_name: str, args: dict) -> str:
    """Stable key to detect duplicate identical tool invocations in one turn."""
    norm = {}
    for k, v in (args or {}).items():
        if isinstance(v, str):
            norm[k] = v.strip()
        elif isinstance(v, list):
            norm[k] = [str(x).strip() if isinstance(x, str) else x for x in v]
        else:
            norm[k] = v
    return f"{tool_name}:{json.dumps(norm, sort_keys=True, ensure_ascii=False)}"


def compact_digest(obj: dict, max_chars: int = 1800) -> str:
    """Serialize tool output compactly for LLM observation without blowing context."""
    raw = json.dumps(obj, ensure_ascii=False, separators=(",", ":"), default=str)
    if len(raw) <= max_chars:
        return raw
    trimmed = dict(obj)
    # Trim heaviest lists proportionally before hard-clipping
    for list_key in ("results", "papers", "trials", "mimicking_compounds", "top_up_genes", "top_down_genes"):
        if isinstance(trimmed.get(list_key), list) and len(trimmed[list_key]) > 5:
            trimmed[list_key] = trimmed[list_key][:5]
            trimmed[f"{list_key}_truncated_for_llm"] = True
            raw = json.dumps(trimmed, ensure_ascii=False, separators=(",", ":"), default=str)
            if len(raw) <= max_chars:
                return raw
    for list_key in ("results", "papers", "trials", "compounds"):
        if isinstance(trimmed.get(list_key), list) and len(trimmed[list_key]) > 3:
            trimmed[list_key] = trimmed[list_key][:3]
            raw = json.dumps(trimmed, ensure_ascii=False, separators=(",", ":"), default=str)
            if len(raw) <= max_chars:
                return raw
    return raw[: max_chars - 24] + '..."}'


def format_session_ledger(session_state: dict | None) -> str:
    """Render a minimal (<250 token) multi-turn state block for DeepSeek."""
    if not session_state:
        return "Session ledger: empty (new research session)."
    lines = []
    if session_state.get("active_case_id") or session_state.get("active_disease"):
        lines.append(
            f"Active disease context: {session_state.get('active_disease') or 'kidney disease'} "
            f"(case={session_state.get('active_case_id') or 'none'})"
        )
    cands = (session_state.get("candidates") or [])[:8]
    if cands:
        cand_strs = [
            f"#{c.get('rank', i + 1)} {c.get('pert_iname') or c.get('pert_id')} "
            f"[{c.get('pert_id')}] (T-DIKI={c.get('tdiki_tier') or 'NA'}"
            + (f", RTPS={c['rtps']}" if c.get("rtps") is not None else "")
            + ")"
            for i, c in enumerate(cands)
        ]
        lines.append("Recent ranked candidates: " + "; ".join(cand_strs))
    lit = session_state.get("literature_by_entity") or {}
    if lit:
        lit_strs = [
            f"{ent}: tier={info.get('evidence_tier')}, pmids={info.get('pmids', [])[:4]}, ncts={info.get('ncts', [])[:3]}"
            for ent, info in list(lit.items())[:5]
        ]
        lines.append("Previously audited evidence: " + " | ".join(lit_strs))
    turns = (session_state.get("turns") or [])[-2:]
    if turns:
        lines.append(
            "Recent turns: "
            + " || ".join(
                f"User='{t.get('query', '')[:80]}' -> Skill={t.get('skill_id')}: {t.get('short_outcome', '')[:120]}"
                for t in turns
            )
        )
    return "\n".join(lines) if lines else "Session ledger: empty."


def build_system_prompt(skill, session_state: dict | None, include_literature: bool = True) -> str:
    """Build deterministic, token-lean system prompt scoped strictly to one SKILL.md."""
    lit_rule = (
        "Literature tools ARE enabled for this turn."
        if include_literature
        else "Literature tools are DISABLED by user toggle for this turn; rely strictly on computational tools."
    )
    sections = ", ".join(skill.output_sections)
    ledger = format_session_ledger(session_state)
    return (
        f"You are NephroAgent (v1.2), a strictly grounded kidney drug-repurposing research agent.\n"
        f"Active Skill: {skill.id} ({skill.name}). Allowed tools ONLY: {', '.join(skill.allowed_tools)}.\n"
        f"{lit_rule}\n\n"
        f"{skill.instructions}\n\n"
        f"GROUNDING & CITATION CONTRACT (MANDATORY):\n"
        f"- Copy numbers (RTPS, tau, T-DIKI prob, Tanimoto, counts) faithfully from tool outputs.\n"
        f"- Cite retrieved papers ONLY as [PMID:<digits>] and trials ONLY as [NCT<8-digits>] from tool outputs or session ledger.\n"
        f"- NEVER invent PMIDs, NCT IDs, BRD IDs, compound names, or numeric scores.\n"
        f"- Resolve ordinal references (#1, #2, top 2, first/second) using the Session Ledger below.\n"
        f"- Batch independent tool calls in a single turn when possible (e.g., profile_compound + explain_tdiki, or search_literature + search_clinical_trials) to minimize latency and tokens.\n"
        f"- MUST follow the Skill's exact `###` numbered headings verbatim and ALWAYS synthesize paper `takeaway` findings cleanly (never omit the Literature & Clinical Synthesis section when literature tools ran).\n"
        f"- Keep output concise (target ~180-280 words total) and strictly English markdown.\n\n"
        f"SESSION LEDGER:\n{ledger}"
    )
