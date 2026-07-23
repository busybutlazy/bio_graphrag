"""T2: expert review persistence — record_expert_review appends one audit row.

Mirrors test_curation.py's change-log assertion. Proves the expert gate leaves the
same append-only trail (graph_change_logs) as curation, and writes nothing else.
"""

import asyncio
import json

import asyncpg
import pytest
from app.core.config import settings
from app.curation.service import record_expert_review

TEST_CASE = "blood_glucose_case_t2_test"


async def _connect() -> asyncpg.Connection:
    return await asyncpg.connect(
        host=settings.postgres_host,
        port=settings.postgres_port,
        database=settings.postgres_db,
        user=settings.postgres_user,
        password=settings.postgres_password,
    )


async def _fetch_latest(target_id: str):
    conn = await _connect()
    try:
        return await conn.fetchrow(
            "SELECT action, target_type, actor, reason, after_state "
            "FROM graph_change_logs WHERE target_id = $1 ORDER BY created_at DESC LIMIT 1",
            target_id,
        )
    finally:
        await conn.close()


async def _count(target_id: str) -> int:
    conn = await _connect()
    try:
        return await conn.fetchval(
            "SELECT count(*) FROM graph_change_logs WHERE target_id = $1", target_id
        )
    finally:
        await conn.close()


async def _cleanup(target_id: str) -> None:
    conn = await _connect()
    try:
        await conn.execute("DELETE FROM graph_change_logs WHERE target_id = $1", target_id)
    finally:
        await conn.close()


@pytest.fixture(autouse=True)
def cleanup():
    yield
    asyncio.run(_cleanup(TEST_CASE))


def test_record_expert_review_writes_one_audit_row():
    change_id = asyncio.run(
        record_expert_review(
            case_id=TEST_CASE,
            decision="agree",
            schema_gap_type=None,
            notes="方向正確,符合原文",
            actor="expert:tester",
        )
    )
    assert change_id and change_id.startswith("change:")

    assert asyncio.run(_count(TEST_CASE)) == 1

    row = asyncio.run(_fetch_latest(TEST_CASE))
    assert row is not None
    assert row["action"] == "expert_review"
    assert row["target_type"] == "expert_demo_case"
    assert row["actor"] == "expert:tester"
    assert row["reason"] == "方向正確,符合原文"

    after = row["after_state"]
    after = json.loads(after) if isinstance(after, str) else after
    assert after == {"decision": "agree", "schema_gap_type": None}


def test_record_expert_review_persists_schema_gap_decision():
    asyncio.run(
        record_expert_review(
            case_id=TEST_CASE,
            decision="cannot",
            schema_gap_type="permissive_effect",
            notes="無法表達",
            actor="expert:tester",
        )
    )
    row = asyncio.run(_fetch_latest(TEST_CASE))
    after = row["after_state"]
    after = json.loads(after) if isinstance(after, str) else after
    assert after == {"decision": "cannot", "schema_gap_type": "permissive_effect"}
