"""Assemble the extraction prompt from a public base template plus an optional,
local-only per-document profile overlay.

The base template (`prompts/graph_extraction_prompt.md`) ships in git and works on
its own. Per-chapter profiles (`prompts/profiles/<name>.profile.md`) are IP kept
out of git; when the named profile is missing locally we fall back to the generic
base so the public repo still runs.
"""

import re
from functools import lru_cache
from pathlib import Path

PROMPTS_DIR = Path(__file__).resolve().parents[2] / "prompts"
BASE_PROMPT_PATH = PROMPTS_DIR / "graph_extraction_prompt.md"
PROFILES_DIR = PROMPTS_DIR / "profiles"

_FENCE_RE = re.compile(r"```text\n(.*?)```", re.DOTALL)


@lru_cache(maxsize=1)
def _load_base_blocks() -> tuple[str, str]:
    """Return (system_prompt, user_template) from the base markdown doc.

    The doc keeps the two runtime blocks as the first two ```text fenced blocks:
    the system prompt, then the user-prompt template. Cached: the base template
    is static at runtime and this is called once per chunk.
    """
    text = BASE_PROMPT_PATH.read_text(encoding="utf-8")
    blocks = _FENCE_RE.findall(text)
    if len(blocks) < 2:
        raise ValueError(
            f"{BASE_PROMPT_PATH} must contain at least two ```text blocks "
            "(system prompt, then user template)"
        )
    return blocks[0].strip(), blocks[1].strip()


def load_profile(profile_name: str | None) -> str:
    """Return the local profile overlay text, or "" when there is none.

    Missing profile files fall back to generic extraction on purpose: the public
    repo has no private profiles yet must still run.
    """
    if not profile_name:
        return ""
    path = PROFILES_DIR / f"{profile_name}.profile.md"
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8").strip()


def build_system_prompt(profile_name: str | None = None) -> str:
    system, _ = _load_base_blocks()
    overlay = load_profile(profile_name)
    if not overlay:
        return system
    return f"{system}\n\n## 章節特化補充(profile: {profile_name})\n\n{overlay}"


def build_user_prompt(
    chunk_id: str,
    existing_concepts: str,
    chunk_text: str,
) -> str:
    _, user_template = _load_base_blocks()
    return user_template.format(
        chunk_id=chunk_id,
        existing_concepts=existing_concepts,
        chunk_text=chunk_text,
    )
