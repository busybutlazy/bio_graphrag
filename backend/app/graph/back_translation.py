"""Deterministic reverse-translation of a graph proposal into expert-facing 白話.

純函式,以結構簽章 pattern-match(P1–P5),**不呼叫 LLM、不用模板引擎**。
專家畫面的「系統理解」由此當場計算,確保專家看到的就是 graph 真正表達的內容。
對應 docs/expert-in-the-loop-plan.md 五.2。

輸入為 case 的 ``proposal`` dict(``proposed_nodes`` / ``proposed_edges`` /
``references_existing`` …)。邊可能引用跨 case 的既有節點,故 label 需由
``build_context`` 事先掃過所有 case 建索引;查不到時退回 humanized id。
"""
from __future__ import annotations

_DIRECTION_ZH = {"INCREASES": "上升", "DECREASES": "下降"}
_TRIGGER_ZH = {"increase": "升高", "decrease": "降低"}


def _humanize(node_id: str) -> str:
    """`hormone:insulin` -> `insulin`(label 查不到時的保底顯示)。"""
    tail = node_id.split(":", 1)[-1] if ":" in node_id else node_id
    return tail.replace("_", " ")


def build_context(cases: list[dict]) -> dict:
    """跨 case 索引,讓 references_existing 的節點也能以真實 label 呈現。

    - ``labels``: node id -> label(所有 case 的 proposed_nodes)。
    - ``effect_to_hormone``: RegulatoryEffect id -> hormone label
      (掃所有 HAS_EFFECT 邊;P4 拮抗要用兩個 effect 背後的激素命名)。
    """
    labels: dict[str, str] = {}
    for case in cases:
        for node in case.get("proposal", {}).get("proposed_nodes", []):
            labels[node["id"]] = node.get("label", node["id"])
    effect_to_hormone: dict[str, str] = {}
    for case in cases:
        for edge in case.get("proposal", {}).get("proposed_edges", []):
            if edge.get("type") == "HAS_EFFECT":
                effect_to_hormone[edge["target"]] = labels.get(
                    edge["source"], _humanize(edge["source"])
                )
    return {"labels": labels, "effect_to_hormone": effect_to_hormone}


def _ok(pattern: str, rule_id: str, text: str) -> dict:
    return {"pattern": pattern, "rule_id": rule_id, "is_gap": False, "text": text}


def render_understanding(proposal: dict, ctx: dict | None = None) -> dict:
    """Return ``{pattern, rule_id, is_gap, text}``.

    ``ctx`` 為 :func:`build_context` 的輸出;省略時 label 退回 humanized id
    (gate 只需判斷 ``is_gap``,不需 ctx)。
    """
    ctx = ctx or {}
    labels = dict(ctx.get("labels", {}))
    effect_to_hormone = ctx.get("effect_to_hormone", {})

    nodes = proposal.get("proposed_nodes", [])
    edges = proposal.get("proposed_edges", [])
    for node in nodes:  # a case's own nodes are authoritative
        labels.setdefault(node["id"], node.get("label", node["id"]))

    def lbl(nid: str) -> str:
        return labels.get(nid) or _humanize(nid)

    types = {n["id"]: n["type"] for n in nodes}
    props = {n["id"]: (n.get("properties") or {}) for n in nodes}

    def edges_of(rel: str) -> list[dict]:
        return [e for e in edges if e.get("type") == rel]

    # --- P2 secretion_trigger --------------------------------------------
    # Var ─REGULATES_SECRETION_OF→ Hormone  +  Structure ─SECRETES→ Hormone
    reg_sec = edges_of("REGULATES_SECRETION_OF")
    secretes = edges_of("SECRETES")
    if reg_sec and secretes:
        rs = reg_sec[0]
        variable = lbl(rs["source"])
        hormone = lbl(rs["target"])
        structure = lbl(secretes[0]["source"])
        trig = _TRIGGER_ZH.get((rs.get("properties") or {}).get("trigger_direction"), "改變")
        return _ok("P2", "secretion_trigger",
                   f"當{variable}{trig}時,{structure}會分泌{hormone}。")

    # --- P4 antagonistic_interaction -------------------------------------
    # Interaction{antagonism} ─USES_EFFECT→ RE×2, ─ON_VARIABLE→ Var
    interactions = [nid for nid, t in types.items()
                    if t == "Interaction" and props[nid].get("interaction_type") == "antagonism"]
    if interactions:
        iid = interactions[0]
        uses = [e for e in edges_of("USES_EFFECT") if e["source"] == iid]
        on_var = [e for e in edges_of("ON_VARIABLE") if e["source"] == iid]
        if len(uses) >= 2 and on_var:
            a = effect_to_hormone.get(uses[0]["target"]) or lbl(uses[0]["target"])
            b = effect_to_hormone.get(uses[1]["target"]) or lbl(uses[1]["target"])
            variable = lbl(on_var[0]["target"])
            return _ok("P4", "antagonistic_interaction",
                       f"{a}與{b}透過方向相反的兩個調控效果,在{variable}上呈現拮抗。")

    # --- P1 / P3 regulatory-effect three-part ----------------------------
    # Hormone ─HAS_EFFECT→ RE ─ON_VARIABLE→ Var, RE ─[INCREASES|DECREASES]→ Var
    has_effect = edges_of("HAS_EFFECT")
    if has_effect:
        he = has_effect[0]
        hormone = lbl(he["source"])
        re_id = he["target"]
        on_var = [e for e in edges_of("ON_VARIABLE") if e["source"] == re_id]
        dir_edges = [e for e in edges if e["source"] == re_id and e.get("type") in _DIRECTION_ZH]
        if on_var and dir_edges:
            variable = lbl(on_var[0]["target"])
            direction = _DIRECTION_ZH[dir_edges[0]["type"]]
            causes = [e for e in edges_of("CAUSES") if e["source"] == he["source"]]
            if causes:  # P3 — mechanism 節點
                process = lbl(causes[0]["target"])
                return _ok("P3", "regulatory_effect_with_mechanism",
                           f"{hormone}會促成{process},並造成調控效果:使{variable}{direction}。")
            return _ok("P1", "single_regulatory_effect",
                       f"{hormone}會造成一個調控效果:使{variable}{direction}。")

    # --- P5 schema gap: no pattern matched -------------------------------
    return {"pattern": "P5", "rule_id": "schema_gap", "is_gap": True,
            "text": "系統目前無法用既有的知識結構完整表達此現象。"}
