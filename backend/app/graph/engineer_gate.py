"""Engineer gate — 只管形式(form),**不碰生物語意**。

複用既有 schema / 型別驗證 + 三段式 / Interaction 完整性 + back_translation 可用性,
對 graph proposal 給出形式判定。對應 docs/expert-in-the-loop-plan.md 五.3。

``result ∈ {pass, fail_schema, fail_pattern, fail_testability, needs_schema_extension}``。
只有硬 schema gap(如 Case 5 permissive effect)→ ``needs_schema_extension``。
"""
from __future__ import annotations

import re

import jsonschema

from ingestion.pipeline.normalize_concepts import (
    VALID_NODE_TYPES,
    VALID_RELATIONSHIP_TYPES,
)
from ingestion.pipeline.validate_extraction import validate_extraction_output

from app.graph.back_translation import render_understanding

# node id 會被插進 Cypher label,故沿用抽取 schema 的 id 慣例(僅檢查節點 id;
# edge id 如 e:c1:has_effect 不插 label,不受此限)。
_ID_RE = re.compile(r"^[a-z_]+:[a-z0-9_]+$")


def _pattern_check(nodes: list[dict], edges: list[dict]) -> str | None:
    """三段式 / Interaction 完整性。OK 回 ``None``,否則回失敗描述。

    只驗證「出現在本 proposal 的」RE / Interaction 是否結構完整;完全沒有關係
    pattern(如 Case 5)不算 pattern 失敗 —— 那由 back_translation 判為 gap。
    """
    types = {n["id"]: n["type"] for n in nodes}

    def out(nid: str, rel: str) -> list[dict]:
        return [e for e in edges if e.get("source") == nid and e.get("type") == rel]

    def inc(nid: str, rel: str) -> list[dict]:
        return [e for e in edges if e.get("target") == nid and e.get("type") == rel]

    for nid, t in types.items():
        if t == "RegulatoryEffect":
            if not inc(nid, "HAS_EFFECT"):
                return f"RegulatoryEffect {nid} 缺 HAS_EFFECT 入邊"
            if not out(nid, "ON_VARIABLE"):
                return f"RegulatoryEffect {nid} 缺 ON_VARIABLE 出邊"
            if not [e for e in edges if e.get("source") == nid
                    and e.get("type") in ("INCREASES", "DECREASES")]:
                return f"RegulatoryEffect {nid} 缺 INCREASES/DECREASES 方向邊"
        if t == "Interaction":
            if len(out(nid, "USES_EFFECT")) < 2:
                return f"Interaction {nid} 需至少兩條 USES_EFFECT"
            if not out(nid, "ON_VARIABLE"):
                return f"Interaction {nid} 缺 ON_VARIABLE"
    return None


def _decide(checks: list[dict]) -> str:
    codes = {c["code"] for c in checks if not c["passed"] and c["code"]}
    for code in ("fail_schema", "fail_pattern", "needs_schema_extension", "fail_testability"):
        if code in codes:
            return code
    return "pass"


def evaluate(proposal: dict) -> dict:
    """Return ``{result, checks}``;``checks`` 為逐項燈號供 Tab2 展示。"""
    nodes = proposal.get("proposed_nodes", [])
    edges = proposal.get("proposed_edges", [])
    checks: list[dict] = []

    def add(name: str, passed: bool, detail: str = "", code: str | None = None) -> None:
        checks.append({"name": name, "passed": passed, "detail": detail,
                       "code": None if passed else code})

    # 1. schema_validation(複用 extraction_output_schema)
    try:
        validate_extraction_output({"nodes": nodes, "edges": edges})
        add("schema_validation", True, "符合 extraction_output_schema")
    except jsonschema.ValidationError as exc:
        add("schema_validation", False, exc.message, "fail_schema")

    # 2. node_type_validation
    bad_nodes = [n.get("id") for n in nodes if n.get("type") not in VALID_NODE_TYPES]
    add("node_type_validation", not bad_nodes,
        "節點型別均在白名單" if not bad_nodes else f"未知節點型別:{bad_nodes}", "fail_schema")

    # 3. edge_type_validation
    bad_edges = [e.get("id") for e in edges if e.get("type") not in VALID_RELATIONSHIP_TYPES]
    add("edge_type_validation", not bad_edges,
        "關係型別均在白名單" if not bad_edges else f"未知關係型別:{bad_edges}", "fail_schema")

    # 4. id_convention_validation(僅節點 id)
    bad_ids = [n.get("id") for n in nodes if not _ID_RE.match(n.get("id", ""))]
    add("id_convention_validation", not bad_ids,
        "節點 id 符合慣例" if not bad_ids else f"節點 id 不符 ^[a-z_]+:[a-z0-9_]+$:{bad_ids}",
        "fail_schema")

    # 5. pattern_validation(三段式 / Interaction 完整性)
    pattern_detail = _pattern_check(nodes, edges)
    add("pattern_validation", pattern_detail is None,
        pattern_detail or "結構完整或無局部 pattern", "fail_pattern")

    # 6. back_translation_available(renderer 能產非 gap 句)
    rendered = render_understanding(proposal)
    add("back_translation_available", not rendered["is_gap"],
        rendered["text"], "needs_schema_extension")

    # 7. testability(已知 pattern → 可導最小斷言)
    testable = not rendered["is_gap"]
    add("testability", testable,
        "可導出最小斷言" if testable else "無 pattern,不導斷言", "fail_testability")

    # 8. duplication_risk(標記不擋)
    dup = [n.get("id") for n in nodes if n.get("possible_duplicate_of")]
    add("duplication_risk", True,
        "無重複疑慮" if not dup else f"疑似重複(標記不擋):{dup}")

    return {"result": _decide(checks), "checks": checks}
