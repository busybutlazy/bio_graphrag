"""The splitter and the expert lens must agree on what a statement is.

`ingestion.pipeline.group_statements` cannot import `back_translation` — the dependency runs
backend → ingestion, never back — so the statement shapes exist in two places. These guards keep the
copies honest.

Three of them, and only one covers the case that actually went wrong:

- each template still renders as the pattern it claims — behavioural, per declared instance;
- a residual group never renders a pattern sentence — behavioural, per declared instance;
- **every pattern the renderer can answer with is either templated or a recorded exclusion** — this
  one reads the pattern ids out of the renderer's own source, so it does not depend on anyone having
  thought of the shape in advance.

That last distinction is the lesson from the review. The first two only ever see hand-written
instances, so a shape nobody thought of is invisible to them — the same blind spot that let P2
(secretion) ship untemplated, since it has no distinctive node type to notice. A guard built out of
human enumeration cannot catch a failure of human enumeration.
"""

import inspect
import re

import pytest
from app.graph import back_translation
from app.graph.back_translation import render_understanding

from ingestion.pipeline.group_statements import _TEMPLATES, split_into_statements

CHUNK = "doc:guard:chunk:000"

# Patterns the renderer can answer with that are NOT statement shapes: the fallbacks it reaches when
# nothing matched. A residual group is allowed to land on these.
_FALLBACK_PATTERNS = {"P0", "P5"}

# Statement shapes the splitter deliberately does not template, with the reason. Anything here is a
# recorded decision; anything *not* here and not templated is an oversight, which is what the
# enumeration guard below is for.
_DELIBERATELY_UNTEMPLATED = {
    "P3": "mechanism (CAUSES) is reviewed apart from the effect — owner decision, 2026-08-11",
}

# One minimal, complete instance per template. Kept hand-written rather than generated: the point is
# to state what each shape looks like, so a reader can check it against the renderer.
_FOCUS = {
    "P2": "hormone:g_ins",
    "P4": "interaction:g_antag",
    "P6": "feedback:g_loop",
    "P1": "regulatory_effect:g_low",
}

_INSTANCES = {
    "P2": {
        "nodes": [
            {"id": "hormone:g_ins", "type": "Hormone", "label": "胰島素", "description": "d"},
            {"id": "structure:g_pan", "type": "Structure", "label": "胰臟", "description": "d"},
            {
                "id": "physiological_variable:g_bg",
                "type": "PhysiologicalVariable",
                "label": "血糖",
                "description": "d",
            },
        ],
        "edges": [
            {
                "id": "e:g1",
                "type": "SECRETES",
                "source": "structure:g_pan",
                "target": "hormone:g_ins",
            },
            {
                "id": "e:g2",
                "type": "REGULATES_SECRETION_OF",
                "source": "physiological_variable:g_bg",
                "target": "hormone:g_ins",
            },
        ],
    },
    "P4": {
        "nodes": [
            {
                "id": "interaction:g_antag",
                "type": "Interaction",
                "label": "拮抗",
                "description": "d",
                "properties": {"interaction_type": "antagonism"},
            },
            {
                "id": "regulatory_effect:g_a",
                "type": "RegulatoryEffect",
                "label": "A",
                "description": "d",
            },
            {
                "id": "regulatory_effect:g_b",
                "type": "RegulatoryEffect",
                "label": "B",
                "description": "d",
            },
            {
                "id": "physiological_variable:g_bg",
                "type": "PhysiologicalVariable",
                "label": "血糖",
                "description": "d",
            },
        ],
        "edges": [
            {
                "id": "e:g3",
                "type": "USES_EFFECT",
                "source": "interaction:g_antag",
                "target": "regulatory_effect:g_a",
            },
            {
                "id": "e:g4",
                "type": "USES_EFFECT",
                "source": "interaction:g_antag",
                "target": "regulatory_effect:g_b",
            },
            {
                "id": "e:g5",
                "type": "ON_VARIABLE",
                "source": "interaction:g_antag",
                "target": "physiological_variable:g_bg",
            },
        ],
    },
    "P6": {
        "nodes": [
            {
                "id": "feedback:g_loop",
                "type": "FeedbackLoop",
                "label": "血糖負回饋",
                "description": "d",
                # 變因寫屬性、只引用一個效果,都是 rule card 記載的刻意選擇
                "properties": {
                    "feedback_type": "negative",
                    "regulated_variable": "g_bg",
                },
            },
            {
                "id": "regulatory_effect:g_a",
                "type": "RegulatoryEffect",
                "label": "降血糖",
                "description": "d",
            },
        ],
        "edges": [
            {
                "id": "e:g9",
                "type": "USES_EFFECT",
                "source": "feedback:g_loop",
                "target": "regulatory_effect:g_a",
            },
        ],
    },
    "P1": {
        "nodes": [
            {"id": "hormone:g_ins", "type": "Hormone", "label": "胰島素", "description": "d"},
            {
                "id": "regulatory_effect:g_low",
                "type": "RegulatoryEffect",
                "label": "降血糖",
                "description": "d",
            },
            {
                "id": "physiological_variable:g_bg",
                "type": "PhysiologicalVariable",
                "label": "血糖",
                "description": "d",
            },
        ],
        "edges": [
            {
                "id": "e:g6",
                "type": "HAS_EFFECT",
                "source": "hormone:g_ins",
                "target": "regulatory_effect:g_low",
            },
            {
                "id": "e:g7",
                "type": "ON_VARIABLE",
                "source": "regulatory_effect:g_low",
                "target": "physiological_variable:g_bg",
            },
            {
                "id": "e:g8",
                "type": "DECREASES",
                "source": "regulatory_effect:g_low",
                "target": "physiological_variable:g_bg",
            },
        ],
    },
}


@pytest.mark.parametrize("pattern", [t[0] for t in _TEMPLATES])
def test_every_template_renders_as_the_pattern_it_claims(pattern):
    """A template that no longer matches its renderer rule would split statements the lens cannot
    describe — the group would look reviewable but read as a bare list of concepts."""
    assert pattern in _INSTANCES, f"no minimal instance declared for template {pattern}"
    candidate = _INSTANCES[pattern]
    groups = {g["group_id"]: g for g in split_into_statements(candidate, CHUNK)}

    # nothing may be left over: a complete statement claims all of its own elements
    assert f"group:llm:{CHUNK}:residual" not in groups, "a complete statement left residue"

    focus = groups[f"group:llm:{CHUNK}:{_FOCUS[pattern]}"]
    proposal = {"proposed_nodes": focus["nodes"], "proposed_edges": focus["edges"]}
    assert render_understanding(proposal)["pattern"] == pattern
    # (a P4 instance also yields a group per referenced effect — each is its own statement, and
    # with no edges of its own the gate will call it incomplete, which is the honest answer)


def test_a_residual_group_never_renders_a_pattern_sentence():
    """The guard that catches a renderer pattern no template covers.

    If such a pattern exists, its members land in the residual bag, the renderer matches it there,
    and the reviewer is shown a confident sentence about part of a bag while approving all of it.
    Feed the splitter every declared shape at once plus unrelated noise: each shape must be claimed
    by its own group, leaving the residual with nothing a pattern rule can latch onto.
    """
    nodes = {n["id"]: n for inst in _INSTANCES.values() for n in inst["nodes"]}
    edges = {e["id"]: e for inst in _INSTANCES.values() for e in inst["edges"]}
    nodes["misconception:g_noise"] = {
        "id": "misconception:g_noise",
        "type": "Misconception",
        "label": "誤解",
        "description": "d",
    }
    edges["e:g_noise"] = {
        "id": "e:g_noise",
        "type": "COMMONLY_CONFUSED_WITH",
        "source": "misconception:g_noise",
        "target": "hormone:g_ins",
    }
    candidate = {"nodes": list(nodes.values()), "edges": list(edges.values())}

    residual = [
        g for g in split_into_statements(candidate, CHUNK) if g["group_id"].endswith(":residual")
    ]
    assert len(residual) == 1
    rendered = render_understanding(
        {"proposed_nodes": residual[0]["nodes"], "proposed_edges": residual[0]["edges"]}
    )
    assert rendered["pattern"] in {"P0", "P5"}, (
        f"the residual bag rendered as {rendered['pattern']} — a renderer pattern has no template, "
        "so its statement is being described inside a bag of unrelated members"
    )


def test_every_pattern_the_renderer_can_answer_with_is_accounted_for():
    """The guard that would actually have caught the original defect.

    The other two guards only ever see hand-written instances, so a pattern nobody thought of is
    invisible to them — the same blind spot that let P2 (secretion) ship untemplated in the first
    place. This one reads the pattern ids out of the renderer itself, so adding a shape there
    without either templating it or recording why not fails here.
    """
    source = inspect.getsource(back_translation)
    answerable = set(re.findall(r'"(P\d+)"', source))
    # Reading source is the only way to enumerate without importing ingestion *into* the renderer,
    # and it assumes the ids stay double-quoted literals. The floor below is the tripwire: if a
    # refactor moves them into an enum or f-string, this fails loudly rather than silently passing
    # on an empty set — which would turn the guard into decoration.
    assert len(answerable) >= len(_TEMPLATES) + len(_FALLBACK_PATTERNS), (
        f"only found {sorted(answerable)} in back_translation — the pattern ids are no longer "
        "plain double-quoted literals, so this guard is not reading them any more"
    )

    shapes = answerable - _FALLBACK_PATTERNS
    templated = {name for name, _focus, _reqs in _TEMPLATES}

    unaccounted = shapes - templated - set(_DELIBERATELY_UNTEMPLATED)
    assert not unaccounted, (
        f"the renderer can describe {sorted(unaccounted)} but the splitter has no template for it — "
        "such a statement falls into the residual bag and gets described there while its bagmates "
        "ride along unseen. Add a template, or record the exclusion in _DELIBERATELY_UNTEMPLATED."
    )
    # and the exclusion list must not rot: everything in it must still be something the renderer says
    assert set(_DELIBERATELY_UNTEMPLATED) <= shapes, (
        "_DELIBERATELY_UNTEMPLATED names a pattern the renderer no longer produces: "
        f"{sorted(set(_DELIBERATELY_UNTEMPLATED) - shapes)}"
    )


def test_no_edge_is_claimed_by_two_templates():
    """Templates are matched in the renderer's precedence order, so an edge two shapes could both
    want must land in exactly one group — otherwise the same claim would be approvable twice, and
    which group got it would depend on declaration order rather than meaning.

    Today no relation type is contested (ON_VARIABLE is shared by P1 and P4 but the focus types
    differ), so this pins a property that currently holds by luck of the type set.
    """
    nodes = {n["id"]: n for inst in _INSTANCES.values() for n in inst["nodes"]}
    edges = {e["id"]: e for inst in _INSTANCES.values() for e in inst["edges"]}
    groups = split_into_statements(
        {"nodes": list(nodes.values()), "edges": list(edges.values())}, CHUNK
    )

    placed = [e["id"] for g in groups for e in g["edges"]]
    assert sorted(placed) == sorted(edges), "an edge was dropped or duplicated across groups"
    assert len(placed) == len(set(placed)), "an edge landed in more than one group"


def test_interaction_and_effect_each_keep_their_own_on_variable():
    """The concrete contested case: ON_VARIABLE appears in both the P4 and P1 shapes."""
    candidate = {
        "nodes": [
            {
                "id": "interaction:c_antag",
                "type": "Interaction",
                "label": "拮抗",
                "description": "d",
                "properties": {"interaction_type": "antagonism"},
            },
            {
                "id": "regulatory_effect:c_a",
                "type": "RegulatoryEffect",
                "label": "A",
                "description": "d",
            },
            {
                "id": "regulatory_effect:c_b",
                "type": "RegulatoryEffect",
                "label": "B",
                "description": "d",
            },
            {"id": "hormone:c_h", "type": "Hormone", "label": "H", "description": "d"},
            {
                "id": "physiological_variable:c_v",
                "type": "PhysiologicalVariable",
                "label": "V",
                "description": "d",
            },
        ],
        "edges": [
            {
                "id": "e:c1",
                "type": "USES_EFFECT",
                "source": "interaction:c_antag",
                "target": "regulatory_effect:c_a",
            },
            {
                "id": "e:c2",
                "type": "USES_EFFECT",
                "source": "interaction:c_antag",
                "target": "regulatory_effect:c_b",
            },
            {
                "id": "e:c3",
                "type": "ON_VARIABLE",
                "source": "interaction:c_antag",
                "target": "physiological_variable:c_v",
            },
            {
                "id": "e:c4",
                "type": "HAS_EFFECT",
                "source": "hormone:c_h",
                "target": "regulatory_effect:c_a",
            },
            {
                "id": "e:c5",
                "type": "ON_VARIABLE",
                "source": "regulatory_effect:c_a",
                "target": "physiological_variable:c_v",
            },
            {
                "id": "e:c6",
                "type": "DECREASES",
                "source": "regulatory_effect:c_a",
                "target": "physiological_variable:c_v",
            },
        ],
    }
    groups = {
        g["group_id"].replace(f"group:llm:{CHUNK}:", ""): g
        for g in split_into_statements(candidate, CHUNK)
    }

    assert {e["id"] for e in groups["interaction:c_antag"]["edges"]} == {"e:c1", "e:c2", "e:c3"}
    assert {e["id"] for e in groups["regulatory_effect:c_a"]["edges"]} == {"e:c4", "e:c5", "e:c6"}
