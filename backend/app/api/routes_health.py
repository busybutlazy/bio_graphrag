from fastapi import APIRouter
from pydantic import BaseModel

from app.db.neo4j_client import check_neo4j
from app.db.postgres import check_postgres
from app.db.qdrant_client import check_qdrant

router = APIRouter()


class DependencyStatus(BaseModel):
    name: str
    ok: bool
    detail: str | None = None


class HealthResponse(BaseModel):
    status: str
    dependencies: list[DependencyStatus]


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    postgres_ok, postgres_detail = await check_postgres()
    neo4j_ok, neo4j_detail = await check_neo4j()
    qdrant_ok, qdrant_detail = check_qdrant()

    dependencies = [
        DependencyStatus(name="postgres", ok=postgres_ok, detail=postgres_detail),
        DependencyStatus(name="neo4j", ok=neo4j_ok, detail=neo4j_detail),
        DependencyStatus(name="qdrant", ok=qdrant_ok, detail=qdrant_detail),
    ]
    status = "ok" if all(dep.ok for dep in dependencies) else "degraded"
    return HealthResponse(status=status, dependencies=dependencies)
