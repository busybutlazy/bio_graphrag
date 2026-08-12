"""Per-element salvage: keep the valid part, disclose the rest.

The behaviour these pin was paid for three times over — a single edge missing its ``id`` used to
discard two complete regulatory triples along with it.
"""

import pytest

from ingestion.extract import runner
from ingestion.extract.salvage import DEGRADED_DROP_RATIO, salvage

CHUNK = "doc:test:chunk:000"


def _node(node_id, node_type="Hormone"):
    return {
        "id": node_id,
        "type": node_type,
        "label": "l",
        "description": "d",
        "source_chunk_id": CHUNK,
    }


def _edge(edge_id, source, target, edge_type="HAS_EFFECT"):
    return {
        "id": edge_id,
        "type": edge_type,
        "source": source,
        "target": target,
        "source_chunk_id": CHUNK,
    }


def test_a_clean_output_is_returned_untouched():
    """The salvage path must not perturb the normal one."""
    raw = {"nodes": [_node("hormone:insulin")], "edges": []}
    result = salvage(raw)
    assert result.candidate == raw
    assert result.dropped == []
    assert result.degraded is False


def test_one_bad_edge_does_not_take_the_chunk_with_it():
    raw = {
        "nodes": [
            _node("hormone:insulin"),
            _node("physiological_variable:bg", "PhysiologicalVariable"),
        ],
        "edges": [
            _edge("e1", "hormone:insulin", "physiological_variable:bg"),
            {"type": "PART_OF", "source": "a", "target": "b", "source_chunk_id": CHUNK},  # no id
        ],
    }
    result = salvage(raw)

    assert [n["id"] for n in result.candidate["nodes"]] == [
        "hormone:insulin",
        "physiological_variable:bg",
    ]
    assert [e["id"] for e in result.candidate["edges"]] == ["e1"]
    assert len(result.dropped) == 1
    assert result.dropped[0]["kind"] == "edge" and result.dropped[0]["id"] is None
    assert "id" in result.dropped[0]["reason"]


def test_an_edge_into_a_dropped_node_is_dropped_too():
    """Plan D1a. Left in, it is exactly the dangling edge ``approve_group`` refuses — the group
    would reach the reviewer unapprovable, with no way out but rejecting good knowledge."""
    raw = {
        "nodes": [_node("hormone:insulin"), {"id": "hormone:bad", "type": "Hormone"}],  # no label
        "edges": [_edge("e1", "hormone:insulin", "hormone:bad")],
    }
    result = salvage(raw)

    assert [n["id"] for n in result.candidate["nodes"]] == ["hormone:insulin"]
    assert result.candidate["edges"] == []
    reasons = {d["id"]: d["reason"] for d in result.dropped}
    assert "hormone:bad" in reasons
    assert "端點已被丟棄" in reasons["e1"]


def test_an_edge_into_a_never_proposed_node_survives():
    """Extractions are told to reference already-curated concepts instead of re-proposing them,
    so an endpoint absent from this chunk is normal — cascading on it would delete correct edges."""
    raw = {
        "nodes": [_node("hormone:insulin")],
        "edges": [_edge("e1", "structure:pancreas", "hormone:insulin", "SECRETES")],
    }
    result = salvage(raw)

    assert [e["id"] for e in result.candidate["edges"]] == ["e1"]
    assert result.dropped == []


def test_nothing_valid_means_the_chunk_still_fails():
    raw = {"nodes": [{"type": "Hormone"}], "edges": []}
    result = salvage(raw)
    assert result.candidate is None
    assert len(result.dropped) == 1


@pytest.mark.parametrize("raw", [None, "text", {"nodes": "x", "edges": []}, {}])
def test_unusable_shapes_salvage_to_nothing(raw):
    assert salvage(raw).candidate is None


def test_losing_more_than_half_flags_degraded_without_blocking():
    """Plan D1b: flag, never block. Blocking restores the whole-chunk loss this exists to end."""
    raw = {
        "nodes": [_node("hormone:insulin"), {"id": "hormone:b"}, {"id": "hormone:c"}],
        "edges": [],
    }
    result = salvage(raw)

    assert result.candidate is not None, "degraded must not block"
    assert [n["id"] for n in result.candidate["nodes"]] == ["hormone:insulin"]
    assert len(result.dropped) / 3 > DEGRADED_DROP_RATIO
    assert result.degraded is True


@pytest.mark.asyncio
async def test_extract_chunk_salvages_after_the_retry_budget():
    """Retry first, salvage second: a corrected full answer beats a pruned one."""
    calls = []

    def flaky(system_prompt, user_prompt):
        calls.append(user_prompt)
        return {
            "nodes": [_node("hormone:insulin")],
            "edges": [{"type": "PART_OF", "source": "a", "target": "b", "source_chunk_id": CHUNK}],
        }, 5

    attempt = await runner._extract_chunk(
        extract_fn=flaky, system_prompt="s", user_prompt="u", retries=1
    )

    assert len(calls) == 2, "salvage must not short-circuit the retry"
    assert [n["id"] for n in attempt.candidate["nodes"]] == ["hormone:insulin"]
    assert attempt.candidate["edges"] == []
    assert attempt.error is None, "a salvaged chunk is not a failed chunk"
    assert len(attempt.dropped) == 1
    assert attempt.tokens == 10
