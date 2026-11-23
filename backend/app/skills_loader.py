"""Declarative SKILL.md loader and deterministic skill selector."""
from dataclasses import dataclass
from pathlib import Path
import re

import yaml

from .agent import _rule_route
from .agent_runner import _extract_compound_candidates

SKILLS_DIR = Path(__file__).resolve().parent / "skills"


@dataclass(frozen=True)
class SkillSpec:
    id: str
    name: str
    short_label: str
    description: str
    color: str
    max_steps: int
    allowed_tools: tuple[str, ...]
    requires_literature: bool
    output_sections: tuple[str, ...]
    example_prompt: str
    instructions: str


_CACHE: dict[str, SkillSpec] | None = None


def _parse_skill_md(path: Path) -> SkillSpec:
    raw = path.read_text(encoding="utf-8")
    if not raw.startswith("---"):
        raise ValueError(f"Missing YAML frontmatter in {path}")
    parts = raw.split("---", 2)
    if len(parts) < 3:
        raise ValueError(f"Malformed frontmatter in {path}")
    meta = yaml.safe_load(parts[1]) or {}
    body = parts[2].strip()
    return SkillSpec(
        id=str(meta["id"]),
        name=str(meta["name"]),
        short_label=str(meta.get("short_label") or meta["name"]),
        description=str(meta["description"]),
        color=str(meta.get("color") or "#2563eb"),
        max_steps=max(1, min(6, int(meta.get("max_steps", 5)))),
        allowed_tools=tuple(meta.get("allowed_tools") or ()),
        requires_literature=bool(meta.get("requires_literature", True)),
        output_sections=tuple(meta.get("output_sections") or ()),
        example_prompt=str(meta.get("example_prompt") or ""),
        instructions=body,
    )


def load_skills(force_reload: bool = False) -> dict[str, SkillSpec]:
    global _CACHE
    if _CACHE is not None and not force_reload:
        return _CACHE
    loaded = {}
    for p in sorted(SKILLS_DIR.glob("*/SKILL.md")):
        spec = _parse_skill_md(p)
        loaded[spec.id] = spec
    _CACHE = loaded
    return _CACHE


def list_skills() -> list[dict]:
    order = [
        "disease-repurposing",
        "toxicity-rescue",
        "target-to-lead",
        "structure-moa-evidence",
        "literature-evidence",
        "compound-compare",
    ]
    skills = load_skills()
    items = [skills[k] for k in order if k in skills] + [
        v for k, v in skills.items() if k not in order
    ]
    return [
        {
            "id": s.id,
            "name": s.name,
            "short_label": s.short_label,
            "description": s.description,
            "color": s.color,
            "max_steps": s.max_steps,
            "allowed_tools": list(s.allowed_tools),
            "requires_literature": s.requires_literature,
            "output_sections": list(s.output_sections),
            "example_prompt": s.example_prompt,
        }
        for s in items
    ]


def get_skill(skill_id: str) -> SkillSpec | None:
    return load_skills().get(skill_id)


_COMPARE_RE = re.compile(
    r"\b(compare|comparison|versus|vs\.?|head[- ]?to[- ]?head|difference between|contrast)\b|"
    r"对比|比较|哪个更好|谁更安全",
    re.I,
)
_LIT_RE = re.compile(
    r"\b(literature|pubmed|europe\s*pmc|papers?|publications?|citations?|clinical\s*trials?|nct\d{6,}|evidence|novelty)\b|"
    r"文献|论文|临床试验|循证|新颖度",
    re.I,
)
_COMPUTE_SCREEN_RE = re.compile(
    r"\b(up:|down:|dkd|ln|igan|aki|ckd|fsgs|cohort|case|inhibit|activate|pathway|smad|ppara|tgfb|knockdown|knockout|mimic|smiles|similar|analog\w*|brd-|repurpos\w*)\b|"
    r"上调|下调|队列|案例|通路|抑制|激活|敲低|敲除|结构|相似|类似物",
    re.I,
)
_ORDINAL_OR_REF_RE = re.compile(
    r"#\s*[1-9]\b|\b(first|second|third|top\s*[234]|previous|above|these|those|them|it)\b|"
    r"第\s*[123一二三]\s*个?|前\s*[23两三]\s*个?|刚才|上面|这些药",
    re.I,
)
_ANALOG_RESCUE_RE = re.compile(
    r"\b(?:safer\b.{0,28}\b(?:analog\w*|alternative\w*)|less\s+toxic|"
    r"nephrotoxic\w*.{0,45}\b(?:analog\w*|alternative\w*)|"
    r"rescue|replace\w*|low[- ]?diki|t-?diki|diril)\b|"
    r"低肾毒类似|更安全.*类似|替代|减毒",
    re.I,
)


def select_skill(
    query: str,
    session_state: dict | None = None,
    preferred_skill: str | None = None,
) -> tuple[SkillSpec | None, dict]:
    """Deterministically route query + session context to one of 6 SKILL.md playbooks or OUT_OF_SCOPE."""
    text = (query or "").strip()
    skills = load_skills()

    if preferred_skill and preferred_skill in skills:
        r = _rule_route(text)
        return skills[preferred_skill], {
            "reason": f"Explicitly selected skill '{preferred_skill}'",
            "sop_hint": r.get("sop_id"),
            "route_params": r.get("params") or {},
        }

    if _COMPARE_RE.search(text):
        return skills["compound-compare"], {
            "reason": "Matched head-to-head comparison keywords",
            "sop_hint": "COMPARE",
            "route_params": {},
        }

    # Toxicity rescue / safer analogs on an active compound or named compound
    if _ANALOG_RESCUE_RE.search(text) and not re.search(
        r"\b(up:|down:|dkd|ln|igan|aki|ckd|fsgs|cohort|case|pathway|signaling|"
        r"inhibit|activate|knockdown|knockout|mimic|smiles|smad|ppara|tgfb)\b|"
        r"上调|下调|队列|案例|通路|抑制|激活|敲低|敲除",
        text,
        re.I,
    ):
        return skills["toxicity-rescue"], {
            "reason": "Matched NephroSafe safety & analog rescue intent",
            "sop_hint": "SOP-2",
            "route_params": {},
        }

    # Pure literature / clinical trials check (either explicit entities or session references)
    has_lit = bool(_LIT_RE.search(text))
    has_screen = bool(_COMPUTE_SCREEN_RE.search(text))
    if has_lit and not has_screen:
        return skills["literature-evidence"], {
            "reason": "Matched literature / clinical trials audit intent",
            "sop_hint": "LIT",
            "route_params": {},
        }

    # Delegate to deterministic SOP router for core 6 workflows
    r = _rule_route(text)
    sop_id = r.get("sop_id", "OUT_OF_SCOPE")

    if sop_id == "OUT_OF_SCOPE":
        has_candidates = bool((session_state or {}).get("candidates"))
        if has_candidates and (_ORDINAL_OR_REF_RE.search(text) or len(_extract_compound_candidates(text)) >= 1):
            return skills["literature-evidence"], {
                "reason": "Follow-up query referencing active session candidates",
                "sop_hint": "SESSION_FOLLOWUP",
                "route_params": {},
            }
        return None, {
            "reason": r.get("message") or "Outside kidney drug-repurposing scope",
            "sop_hint": "OUT_OF_SCOPE",
            "route_params": {},
        }

    sop_to_skill = {
        "SOP-1": "disease-repurposing",
        "SOP-3": "disease-repurposing",
        "SOP-6": "disease-repurposing",
        "SOP-2": "toxicity-rescue",
        "SOP-4": "target-to-lead",
        "SOP-5": "structure-moa-evidence",
    }
    sid = sop_to_skill.get(sop_id, "disease-repurposing")
    return skills[sid], {
        "reason": f"Deterministic route {sop_id} -> {sid}",
        "sop_hint": sop_id,
        "route_params": r.get("params") or {},
    }
