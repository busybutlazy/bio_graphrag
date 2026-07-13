"""Admin ingest endpoints.

Three-endpoint surface, deliberately split so the *interface* is public while
the *action* is locked:

- ``GET  /admin/ingest/options``  — chunk strategies + params, available
  extraction profiles, and ingestable source files. Browsable with any admin
  key so an interviewer can see the design.
- ``POST /admin/ingest/preview``  — dry run: parse + chunk + assemble the exact
  prompts, zero token spend, zero writes. Also admin-key only.
- ``POST /admin/ingest/run``      — the real thing: spends tokens, stages
  proposed nodes/edges for curation, writes chunks/embeddings. Gated by the
  owner-only ``X-Ingest-Owner-Token`` on top of the admin key.

The runner itself lives in ``ingestion.extract.runner``; this module only maps
HTTP ⇆ runner and owns source-file resolution + DB handles.
"""

from __future__ import annotations

from pathlib import Path

import asyncpg
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from qdrant_client import QdrantClient

from app.api.auth import require_admin, require_ingest_owner
from app.api.errors import APIError
from app.core.config import settings
from app.db.neo4j_driver import get_driver
from ingestion.extract import chunkers, llm_client
from ingestion.extract import runner as ingest_runner
from ingestion.pipeline import build_extraction_prompt, parse_source

router = APIRouter(prefix="/admin/ingest", dependencies=[Depends(require_admin)])

# Derive paths from the ingestion package (which sits at the repo root in both
# the host checkout and the flattened container layout) rather than from this
# file's depth, which differs between the two.
_DATA_ROOT = parse_source.DATA_DIR.parent  # .../data
_REPO_ROOT = _DATA_ROOT.parent
# Source chapters may be public demo (data/sample) or private IP (data/private).
_SOURCE_DIRS = [
    _DATA_ROOT / "sample" / "chapters",
    _DATA_ROOT / "private" / "chapters",
]
_PROFILES_DIR = build_extraction_prompt.PROFILES_DIR


# --- request models -----------------------------------------------------------


class ChunkParams(BaseModel):
    """Params for the chosen strategy; only the relevant ones are used."""

    chunk_size: int | None = Field(default=None, ge=50, le=5000)
    chunk_overlap: int | None = Field(default=None, ge=0, le=2000)
    max_section_size: int | None = Field(default=None, ge=100, le=8000)


class IngestRequest(BaseModel):
    source: str = Field(
        description="source key from GET /options, e.g. data/sample/chapters/demo.md"
    )
    strategy: str = Field(default=ingest_runner.DEFAULT_STRATEGY)
    chunk_params: ChunkParams = Field(default_factory=ChunkParams)


# --- source resolution --------------------------------------------------------


def _list_sources() -> list[dict]:
    sources: list[dict] = []
    for directory in _SOURCE_DIRS:
        if not directory.is_dir():
            continue
        scope = directory.parent.name  # "sample" or "private"
        for path in sorted(directory.glob("*.md")):
            sources.append(
                {
                    "key": str(path.relative_to(_REPO_ROOT)),
                    "filename": path.name,
                    "scope": scope,
                }
            )
    return sources


def _resolve_source(key: str) -> Path:
    """Map a source key to an absolute path, rejecting anything outside the
    allowed chapter directories (path-traversal guard)."""
    candidate = (_REPO_ROOT / key).resolve()
    for directory in _SOURCE_DIRS:
        if (
            candidate.is_relative_to(directory.resolve())
            and candidate.is_file()
            and candidate.suffix == ".md"
        ):
            return candidate
    raise APIError(404, "source_not_found", f"找不到可匯入的來源檔:{key}")


def _list_profiles() -> list[str]:
    if not _PROFILES_DIR.is_dir():
        return []
    return sorted(p.name[: -len(".profile.md")] for p in _PROFILES_DIR.glob("*.profile.md"))


# --- endpoints ----------------------------------------------------------------


@router.get("/options")
async def ingest_options() -> dict:
    """Everything a caller needs to build a valid preview/run request."""
    return {
        "strategies": [
            {
                "name": "fixed",
                "description": "固定字數硬切,可設重疊",
                "params": ["chunk_size", "chunk_overlap"],
            },
            {
                "name": "recursive",
                "description": "依段落/句子階層遞迴切分,字數控制",
                "params": ["chunk_size", "chunk_overlap"],
            },
            {
                "name": "markdown_header",
                "description": "依 markdown/HTML 標題切段,過長段落退回 recursive",
                "params": ["max_section_size"],
            },
        ],
        "default_strategy": ingest_runner.DEFAULT_STRATEGY,
        "profiles": _list_profiles(),
        "sources": _list_sources(),
        "run_requires_owner_token": True,
    }


@router.post("/preview")
async def ingest_preview(body: IngestRequest) -> dict:
    """Dry run: chunk + assemble prompts, no token spend, no DB writes."""
    _validate_strategy(body.strategy)
    source_path = _resolve_source(body.source)
    report = await ingest_runner.ingest_document(
        source_path=source_path,
        strategy=body.strategy,
        chunk_params=body.chunk_params.model_dump(exclude_none=True),
        dry_run=True,
        neo4j_driver=get_driver(),
    )
    return report.to_dict()


@router.post("/run", dependencies=[Depends(require_ingest_owner)])
async def ingest_run(body: IngestRequest) -> dict:
    """Owner-only: run the real ingest and stage proposed graph changes."""
    _validate_strategy(body.strategy)
    source_path = _resolve_source(body.source)
    if not llm_client.is_configured():
        raise APIError(
            400,
            "llm_not_configured",
            "尚未設定 OPENAI_API_KEY,無法執行知識抽取(離線示範請改用 seed 管線)。",
        )

    pg_conn = await asyncpg.connect(
        host=settings.postgres_host,
        port=settings.postgres_port,
        database=settings.postgres_db,
        user=settings.postgres_user,
        password=settings.postgres_password,
    )
    qdrant = QdrantClient(url=settings.qdrant_url)
    try:
        report = await ingest_runner.ingest_document(
            source_path=source_path,
            strategy=body.strategy,
            chunk_params=body.chunk_params.model_dump(exclude_none=True),
            dry_run=False,
            pg_conn=pg_conn,
            qdrant=qdrant,
            neo4j_driver=get_driver(),
        )
    finally:
        await pg_conn.close()
    return report.to_dict()


def _validate_strategy(strategy: str) -> None:
    if strategy not in chunkers.available_strategies():
        raise APIError(
            422,
            "unknown_strategy",
            f"未知的 chunk 策略 {strategy!r};可用:{chunkers.available_strategies()}",
        )
