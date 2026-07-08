import anyio
from fastapi import APIRouter, HTTPException, Query

from app.db import chunks as chunks_db
from app.db.neo4j_driver import get_driver
from app.graph.cypher_templates import expand_from_seeds, fetch_neighbors, fetch_node_detail
from app.rag.pipeline import MAX_RETURNED_NODES
from app.schemas.graph import NeighborsResponse
from app.schemas.query import ConceptMapRequest, ConceptMapResponse, NodeDetailResponse

router = APIRouter()


@router.get("/nodes/{node_id}", response_model=NodeDetailResponse)
def get_node(node_id: str) -> NodeDetailResponse:
    detail = fetch_node_detail(get_driver(), node_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Node not found")
    return NodeDetailResponse(**detail)


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


@router.post("/concept-map", response_model=ConceptMapResponse)
async def concept_map(body: ConceptMapRequest) -> ConceptMapResponse:
    if body.node_ids:
        seed_ids = body.node_ids
    else:
        seed_ids = await chunks_db.concept_ids_by_topic(body.topic)

    subgraph = await anyio.to_thread.run_sync(
        expand_from_seeds, get_driver(), seed_ids, body.depth, MAX_RETURNED_NODES
    )
    return ConceptMapResponse(nodes=subgraph["nodes"], edges=subgraph["edges"])
