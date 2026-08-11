"""T1: splitting one chunk's extraction output into one review group per statement.

The property under test is the one that motivated the change: a group must hold exactly one
statement, because the expert lens describes only the first pattern it finds — a group with two
statements shows the reviewer half of what they are approving.
"""

from ingestion.pipeline.group_statements import split_into_statements

CHUNK = "doc:test:chunk:000"


def _n(node_id, node_type, label="l"):
    return {"id": node_id, "type": node_type, "label": label, "description": "d"}


def _e(edge_id, edge_type, source, target):
    return {"id": edge_id, "type": edge_type, "source": source, "target": target}


# 胰島素 ─HAS_EFFECT→ RE1 ─ON_VARIABLE/DECREASES→ 血糖
# 升糖素 ─HAS_EFFECT→ RE2 ─ON_VARIABLE/INCREASES→ 血糖     (血糖 shared by both)
_TWO_STATEMENTS = {
    "nodes": [
        _n("hormone:insulin", "Hormone", "胰島素"),
        _n("hormone:glucagon", "Hormone", "升糖素"),
        _n("regulatory_effect:lower_bg", "RegulatoryEffect", "降血糖"),
        _n("regulatory_effect:raise_bg", "RegulatoryEffect", "升血糖"),
        _n("physiological_variable:bg", "PhysiologicalVariable", "血糖"),
    ],
    "edges": [
        _e("e:1", "HAS_EFFECT", "hormone:insulin", "regulatory_effect:lower_bg"),
        _e("e:2", "ON_VARIABLE", "regulatory_effect:lower_bg", "physiological_variable:bg"),
        _e("e:3", "DECREASES", "regulatory_effect:lower_bg", "physiological_variable:bg"),
        _e("e:4", "HAS_EFFECT", "hormone:glucagon", "regulatory_effect:raise_bg"),
        _e("e:5", "ON_VARIABLE", "regulatory_effect:raise_bg", "physiological_variable:bg"),
        _e("e:6", "INCREASES", "regulatory_effect:raise_bg", "physiological_variable:bg"),
    ],
}


def test_two_statements_split_and_share_their_common_variable():
    """The core case. One chunk, two claims, one variable in common."""
    groups = split_into_statements(_TWO_STATEMENTS, CHUNK)

    assert len(groups) == 2, "two anchors must not collapse into one reviewable unit"
    assert [g["group_id"] for g in groups] == [
        f"group:llm:{CHUNK}:regulatory_effect:lower_bg",
        f"group:llm:{CHUNK}:regulatory_effect:raise_bg",
    ]

    lower, raise_ = groups
    assert {n["id"] for n in lower["nodes"]} == {
        "regulatory_effect:lower_bg",
        "hormone:insulin",
        "physiological_variable:bg",
    }
    assert {e["id"] for e in lower["edges"]} == {"e:1", "e:2", "e:3"}
    assert {n["id"] for n in raise_["nodes"]} == {
        "regulatory_effect:raise_bg",
        "hormone:glucagon",
        "physiological_variable:bg",
    }
    assert {e["id"] for e in raise_["edges"]} == {"e:4", "e:5", "e:6"}

    # the shared variable belongs to BOTH statements; the review unit is the claim, not the concept
    assert all("physiological_variable:bg" in {n["id"] for n in g["nodes"]} for g in groups)
    # no residual group: every element was claimed by an anchor
    assert not any(g["group_id"].endswith(":residual") for g in groups)


def test_no_pattern_yields_a_single_residual_group():
    """A misconception chunk matches no template and has no anchor, but is still worth reviewing."""
    candidate = {
        "nodes": [
            _n("misconception:insulin_raises", "Misconception", "誤以為胰島素升血糖"),
            _n("hormone:insulin", "Hormone", "胰島素"),
        ],
        "edges": [
            _e("e:m", "COMMONLY_CONFUSED_WITH", "misconception:insulin_raises", "hormone:insulin")
        ],
    }
    groups = split_into_statements(candidate, CHUNK)

    assert len(groups) == 1
    assert groups[0]["group_id"] == f"group:llm:{CHUNK}:residual"
    assert len(groups[0]["nodes"]) == 2
    assert len(groups[0]["edges"]) == 1


def test_mixed_chunk_splits_into_pattern_group_plus_residual():
    candidate = {
        "nodes": [
            _n("hormone:insulin", "Hormone"),
            _n("regulatory_effect:lower_bg", "RegulatoryEffect"),
            _n("physiological_variable:bg", "PhysiologicalVariable"),
            _n("structure:pancreas", "Structure"),
            _n("system:endocrine", "System"),
        ],
        "edges": [
            _e("e:1", "HAS_EFFECT", "hormone:insulin", "regulatory_effect:lower_bg"),
            _e("e:2", "ON_VARIABLE", "regulatory_effect:lower_bg", "physiological_variable:bg"),
            _e("e:3", "DECREASES", "regulatory_effect:lower_bg", "physiological_variable:bg"),
            # unrelated to the effect: pancreas is part of the endocrine system
            _e("e:4", "PART_OF", "structure:pancreas", "system:endocrine"),
        ],
    }
    groups = split_into_statements(candidate, CHUNK)

    assert len(groups) == 2
    assert groups[-1]["group_id"] == f"group:llm:{CHUNK}:residual"
    assert {n["id"] for n in groups[-1]["nodes"]} == {"structure:pancreas", "system:endocrine"}
    assert {e["id"] for e in groups[-1]["edges"]} == {"e:4"}


def test_incomplete_pattern_still_forms_its_own_group():
    """Splitting is not validation. An anchor missing ON_VARIABLE/direction still gets its own
    group so the Schema gate can answer fail_pattern and the reviewer can turn it away — dropping
    it here would hide a defective proposal instead of surfacing it."""
    candidate = {
        "nodes": [
            _n("hormone:insulin", "Hormone"),
            _n("regulatory_effect:lower_bg", "RegulatoryEffect"),
        ],
        "edges": [_e("e:1", "HAS_EFFECT", "hormone:insulin", "regulatory_effect:lower_bg")],
    }
    groups = split_into_statements(candidate, CHUNK)

    assert len(groups) == 1
    assert groups[0]["group_id"] == f"group:llm:{CHUNK}:regulatory_effect:lower_bg"
    assert {n["id"] for n in groups[0]["nodes"]} == {
        "regulatory_effect:lower_bg",
        "hormone:insulin",
    }


def test_empty_output_yields_no_groups():
    assert split_into_statements({"nodes": [], "edges": []}, CHUNK) == []
    assert split_into_statements({}, CHUNK) == []


def test_nested_anchors_reference_each_other_instead_of_absorbing():
    """T1b: an Interaction's USES_EFFECT points at a RegulatoryEffect, so both endpoints anchor a
    statement. Neither may swallow the other — otherwise two groups propose the same node and the
    second approval collides with the first."""
    candidate = {
        "nodes": [
            _n("interaction:insulin_glucagon", "Interaction", "胰島素與升糖素的拮抗"),
            _n("regulatory_effect:lower_bg", "RegulatoryEffect", "降血糖"),
        ],
        "edges": [
            _e(
                "e:uses",
                "USES_EFFECT",
                "interaction:insulin_glucagon",
                "regulatory_effect:lower_bg",
            )
        ],
    }
    groups = {g["group_id"].rsplit(":", 1)[-1]: g for g in split_into_statements(candidate, CHUNK)}
    assert set(groups) == {"insulin_glucagon", "lower_bg"}

    interaction = groups["insulin_glucagon"]
    effect = groups["lower_bg"]

    # the edge belongs to the source anchor only — never to both
    assert [e["id"] for e in interaction["edges"]] == ["e:uses"]
    assert effect["edges"] == []
    # and neither anchor appears inside the other's membership
    assert {n["id"] for n in interaction["nodes"]} == {"interaction:insulin_glucagon"}
    assert {n["id"] for n in effect["nodes"]} == {"regulatory_effect:lower_bg"}


# Captured from a real gpt-4o-mini extraction of endocrine_demo_v1.md (Task 1.5, 2026-08-11).
# Kept verbatim — including the model's misuse of HAS_EFFECT as RegulatoryEffect→Variable, which is
# what a real chunk actually looks like today. Splitting must behave on the real shape, not an
# idealised one; the wrong relation type is the Schema gate's problem, not the splitter's.
_REAL_EXTRACTION = {
    "nodes": [
        _n(
            "regulatory_effect:insulin_decreases_blood_glucose",
            "RegulatoryEffect",
            "胰島素降低血糖",
        ),
        _n(
            "regulatory_effect:glucagon_increases_blood_glucose",
            "RegulatoryEffect",
            "升糖素提高血糖",
        ),
        _n(
            "interaction:insulin_glucagon_blood_glucose",
            "Interaction",
            "胰島素與升糖素的作用於血糖",
        ),
        _n(
            "regulatory_effect:adh_decreases_blood_osmolarity",
            "RegulatoryEffect",
            "ADH降低血液滲透壓",
        ),
        _n(
            "misconception:insulin_raises_blood_glucose",
            "Misconception",
            "學生誤以為胰島素會提高血糖",
        ),
    ],
    "edges": [
        _e(
            "edge:insulin_decreases_blood_glucose",
            "HAS_EFFECT",
            "regulatory_effect:insulin_decreases_blood_glucose",
            "physiological_variable:blood_glucose",
        ),
        _e(
            "edge:glucagon_increases_blood_glucose",
            "HAS_EFFECT",
            "regulatory_effect:glucagon_increases_blood_glucose",
            "physiological_variable:blood_glucose",
        ),
        _e(
            "edge:insulin_glucagon_interaction",
            "USES_EFFECT",
            "interaction:insulin_glucagon_blood_glucose",
            "regulatory_effect:insulin_decreases_blood_glucose",
        ),
        _e(
            "edge:adh_decreases_blood_osmolarity",
            "HAS_EFFECT",
            "regulatory_effect:adh_decreases_blood_osmolarity",
            "physiological_variable:blood_osmolarity",
        ),
    ],
}


def test_real_extraction_output_splits_without_anchor_cross_contamination():
    """Regression on the shape that stopped Task 1.5 and forced this rule."""
    groups = split_into_statements(_REAL_EXTRACTION, CHUNK)
    assert len(groups) == 5  # 4 anchors + residual (the misconception)

    anchor_ids = {
        n["id"]
        for n in _REAL_EXTRACTION["nodes"]
        if n["type"] in ("RegulatoryEffect", "Interaction")
    }
    for group in groups:
        own_anchor = group["group_id"].replace(f"group:llm:{CHUNK}:", "")
        foreign = {n["id"] for n in group["nodes"]} & anchor_ids - {own_anchor}
        assert not foreign, f"{group['group_id']} absorbed another anchor: {foreign}"

    # every edge landed in exactly one group
    placed = [e["id"] for g in groups for e in g["edges"]]
    assert sorted(placed) == sorted(e["id"] for e in _REAL_EXTRACTION["edges"])

    # the interaction keeps its USES_EFFECT; the effect it references keeps only its own edge
    by_group = {g["group_id"].replace(f"group:llm:{CHUNK}:", ""): g for g in groups}
    assert [e["id"] for e in by_group["interaction:insulin_glucagon_blood_glucose"]["edges"]] == [
        "edge:insulin_glucagon_interaction"
    ]
    assert [
        e["id"] for e in by_group["regulatory_effect:insulin_decreases_blood_glucose"]["edges"]
    ] == ["edge:insulin_decreases_blood_glucose"]
    # the isolated misconception is the residual group
    assert [n["id"] for n in by_group["residual"]["nodes"]] == [
        "misconception:insulin_raises_blood_glucose"
    ]


def test_group_ids_are_deterministic_across_calls():
    """Staging scopes item_id by group_id, so a non-deterministic group id would duplicate the
    entire review queue on a re-ingest of the same chapter."""
    first = split_into_statements(_TWO_STATEMENTS, CHUNK)
    second = split_into_statements(_TWO_STATEMENTS, CHUNK)
    assert [g["group_id"] for g in first] == [g["group_id"] for g in second]
    # and the chunk id is what scopes them — a different chunk yields different groups
    other = split_into_statements(_TWO_STATEMENTS, "doc:test:chunk:001")
    assert {g["group_id"] for g in first}.isdisjoint({g["group_id"] for g in other})


# --- template-based splitting (revision 4, after the independent review) ------------------


def test_secretion_statement_forms_its_own_group():
    """P2 has no distinctive node type — it converges on a Hormone via two incoming edges. Keying
    on node types alone could never give it a group, so it always fell into residual and got
    described there while its bagmates rode along (review finding H2)."""
    candidate = {
        "nodes": [
            _n("hormone:insulin", "Hormone", "胰島素"),
            _n("structure:pancreas", "Structure", "胰臟"),
            _n("physiological_variable:bg", "PhysiologicalVariable", "血糖"),
            _n("misconception:enzyme", "Misconception", "誤以為激素是酵素"),
        ],
        "edges": [
            _e("e:sec", "SECRETES", "structure:pancreas", "hormone:insulin"),
            _e("e:reg", "REGULATES_SECRETION_OF", "physiological_variable:bg", "hormone:insulin"),
            _e("e:conf", "COMMONLY_CONFUSED_WITH", "misconception:enzyme", "hormone:insulin"),
        ],
    }
    groups = {
        g["group_id"].replace(f"group:llm:{CHUNK}:", ""): g
        for g in split_into_statements(candidate, CHUNK)
    }

    assert set(groups) == {"hormone:insulin", "residual"}
    secretion = groups["hormone:insulin"]
    assert {e["id"] for e in secretion["edges"]} == {"e:sec", "e:reg"}
    assert {n["id"] for n in secretion["nodes"]} == {
        "hormone:insulin",
        "structure:pancreas",
        "physiological_variable:bg",
    }
    # the unrelated misconception is NOT swept into the secretion statement
    assert "misconception:enzyme" not in {n["id"] for n in secretion["nodes"]}


def test_mechanism_is_reviewed_apart_from_the_effect():
    """Domain decision: `Hormone ─CAUSES→ Process` is its own claim, not part of the three-part
    effect. The renderer's P3 (which describes both in one sentence) therefore cannot fire on the
    extraction path — recorded in api_contract.md."""
    candidate = {
        "nodes": [
            _n("hormone:insulin", "Hormone", "胰島素"),
            _n("regulatory_effect:lower_bg", "RegulatoryEffect", "降血糖"),
            _n("physiological_variable:bg", "PhysiologicalVariable", "血糖"),
            _n("process:uptake", "Process", "葡萄糖進入細胞"),
        ],
        "edges": [
            _e("e:1", "HAS_EFFECT", "hormone:insulin", "regulatory_effect:lower_bg"),
            _e("e:2", "ON_VARIABLE", "regulatory_effect:lower_bg", "physiological_variable:bg"),
            _e("e:3", "DECREASES", "regulatory_effect:lower_bg", "physiological_variable:bg"),
            _e("e:4", "CAUSES", "hormone:insulin", "process:uptake"),
        ],
    }
    groups = {
        g["group_id"].replace(f"group:llm:{CHUNK}:", ""): g
        for g in split_into_statements(candidate, CHUNK)
    }

    assert set(groups) == {"regulatory_effect:lower_bg", "residual"}
    assert {e["id"] for e in groups["regulatory_effect:lower_bg"]["edges"]} == {"e:1", "e:2", "e:3"}
    assert [e["id"] for e in groups["residual"]["edges"]] == ["e:4"]


def test_no_group_ever_carries_a_dangling_endpoint():
    """Review finding B1: residual edges used to point at nodes another group had taken, so the
    group could not be approved — and if that other group was rejected, never could be."""
    candidate = {
        "nodes": [
            _n("hormone:insulin", "Hormone"),
            _n("regulatory_effect:lower_bg", "RegulatoryEffect"),
            _n("physiological_variable:bg", "PhysiologicalVariable"),
            _n("structure:pancreas", "Structure"),
            _n("misconception:enzyme", "Misconception"),
        ],
        "edges": [
            _e("e:1", "HAS_EFFECT", "hormone:insulin", "regulatory_effect:lower_bg"),
            _e("e:2", "ON_VARIABLE", "regulatory_effect:lower_bg", "physiological_variable:bg"),
            _e("e:3", "DECREASES", "regulatory_effect:lower_bg", "physiological_variable:bg"),
            _e("e:4", "SECRETES", "structure:pancreas", "hormone:insulin"),
            _e("e:5", "COMMONLY_CONFUSED_WITH", "misconception:enzyme", "hormone:insulin"),
        ],
    }
    for group in split_into_statements(candidate, CHUNK):
        member_ids = {n["id"] for n in group["nodes"]}
        endpoints = {ep for e in group["edges"] for ep in (e["source"], e["target"])}
        proposed_here = {n["id"] for n in candidate["nodes"]}
        # every endpoint is either a member of this group, or lives outside the extraction output
        # entirely (an already-approved concept the edge merely references)
        assert not (endpoints & proposed_here) - member_ids, group["group_id"]


def test_anchor_to_anchor_edge_lands_where_the_gate_reads_it():
    """Review finding M1: 'source wins' only agreed with the gate by accident. HAS_EFFECT is checked
    as an *incoming* edge of the RegulatoryEffect, so if both ends anchor, the target must own it —
    otherwise the target loses the edge its own pattern rule requires."""
    candidate = {
        "nodes": [
            _n("regulatory_effect:upstream", "RegulatoryEffect"),
            _n("regulatory_effect:downstream", "RegulatoryEffect"),
        ],
        "edges": [
            _e(
                "e:chain",
                "HAS_EFFECT",
                "regulatory_effect:upstream",
                "regulatory_effect:downstream",
            )
        ],
    }
    groups = {
        g["group_id"].replace(f"group:llm:{CHUNK}:", ""): g
        for g in split_into_statements(candidate, CHUNK)
    }

    assert [e["id"] for e in groups["regulatory_effect:downstream"]["edges"]] == ["e:chain"]
    assert groups["regulatory_effect:upstream"]["edges"] == []
