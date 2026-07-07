from fastapi import APIRouter, HTTPException, Query

from app.db.neo4j_driver import get_driver
from app.graph.cypher_templates import fetch_neighbors
from app.schemas.graph import NeighborsResponse

router = APIRouter()


@router.get("/neighbors/{node_id}", response_model=NeighborsResponse)
def get_neighbors(
    node_id: str,
    depth: int = Query(default=1, ge=1, le=2),
    limit: int = Query(default=30, ge=1, le=30),
) -> NeighborsResponse:
    result = fetch_neighbors(get_driver(), node_id, depth, limit)
    if result is None:
        raise HTTPException(status_code=404, detail="Node not found")
    return NeighborsResponse(**result, depth=depth)
