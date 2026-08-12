import re

from ingestion.pipeline import build_extraction_prompt as bep
from ingestion.pipeline.normalize_concepts import (
    PATTERN_ANCHOR_TYPES,
    VALID_RELATIONSHIP_TYPES,
)

RULE_CARDS_DIR = bep.PROMPTS_DIR.parent / "schema" / "rule_cards"

# The 結構簽章 block is the rule card's normative shape; anything outside it (常見誤解,
# 反向翻譯模板) names relations only in prose and must not be read as a requirement.
_SIGNATURE_RE = re.compile(r"## 結構簽章\n+```\n(.*?)```", re.DOTALL)


# Rule 2 enumerates every allowed relationship type as a bare list of names. That list is
# what the guard must NOT count as coverage: the original defect was precisely a prompt that
# named the types and never said which way they point, so a check satisfied by the whitelist
# would pass on the very prompt it exists to reject.
_WHITELIST_RE = re.compile(r"2\. 只能使用以下 relationship type.*?(?=\n\d+\. )", re.DOTALL)


def _required_relations(card_text: str) -> set[str]:
    match = _SIGNATURE_RE.search(card_text)
    assert match, "rule card 缺 結構簽章 區塊"
    return {tok for tok in re.findall(r"[A-Z_]{3,}", match.group(1)) if tok in VALID_RELATIONSHIP_TYPES}


def _prompt_without_type_whitelist() -> str:
    system = bep.build_system_prompt(None)
    stripped = _WHITELIST_RE.sub("", system)
    assert stripped != system, "找不到 relationship type 白名單區塊,守衛的前提已失效"
    return stripped


def test_base_prompt_covers_every_rule_card_signature():
    """The prompt is a fourth copy of rules that live in engineer_gate, group_statements and
    the rule cards — and the only copy with no other guard. A pattern the prompt states
    nowhere but the type whitelist is one the model cannot be expected to build correctly,
    which is how P2 (secretion trigger) went missing: SECRETES/REGULATES_SECRETION_OF were
    listed as legal names with no shape, so those statements came back as a fabricated
    RegulatoryEffect that passes the Schema gate and only an expert can catch.
    """
    body = _prompt_without_type_whitelist()
    cards = sorted(RULE_CARDS_DIR.glob("*.md"))
    assert cards, "找不到 rule cards"
    for card in cards:
        for relation in sorted(_required_relations(card.read_text(encoding="utf-8"))):
            assert relation in body, (
                f"{card.name} 的 {relation} 只出現在型別白名單,base prompt 沒有說明它的結構與方向"
            )


def test_base_prompt_mentions_every_pattern_anchor_type():
    system = bep.build_system_prompt(None)
    for anchor in sorted(PATTERN_ANCHOR_TYPES):
        assert anchor in system, f"{anchor} 是 gate 的 pattern anchor,base prompt 必須說明其結構"


def test_base_system_prompt_has_no_overlay_when_profile_missing():
    system = bep.build_system_prompt("does_not_exist")
    assert "章節特化補充" not in system
    assert "extraction agent" in system


def test_none_profile_returns_generic_system_prompt():
    assert bep.build_system_prompt(None) == bep.build_system_prompt("")


def test_profile_overlay_is_appended(tmp_path, monkeypatch):
    profile_dir = tmp_path / "profiles"
    profile_dir.mkdir()
    (profile_dir / "endocrine.profile.md").write_text(
        "優先 node type:Hormone, Receptor", encoding="utf-8"
    )
    monkeypatch.setattr(bep, "PROFILES_DIR", profile_dir)

    system = bep.build_system_prompt("endocrine")
    assert "章節特化補充(profile: endocrine)" in system
    assert "優先 node type:Hormone, Receptor" in system


def test_user_prompt_substitutes_placeholders():
    user = bep.build_user_prompt(
        chunk_id="chunk:1",
        existing_concepts="- c1: 胰島素",
        chunk_text="胰島素降低血糖。",
    )
    assert "chunk_id: chunk:1" in user
    assert "胰島素降低血糖。" in user
    assert "- c1: 胰島素" in user
