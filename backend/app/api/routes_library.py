from fastapi import APIRouter
from pydantic import BaseModel

from app.db import chunks as chunks_db
from app.db.neo4j_driver import get_driver
from app.graph.cypher_templates import fetch_nodes_brief, graph_counts
from app.schemas.graph import NodeRef

router = APIRouter()

# Human-readable labels for the sample topics.
TOPIC_LABELS = {
    "blood_glucose_regulation": "血糖調控",
    "water_balance": "水分恆定",
    "calcium_homeostasis": "鈣離子恆定",
    "positive_feedback": "正回饋（分娩）",
}


class LibraryGroup(BaseModel):
    topic: str
    label: str
    count: int
    nodes: list[NodeRef]


class LibraryResponse(BaseModel):
    groups: list[LibraryGroup]
    total_nodes: int
    total_edges: int
    total_topics: int


@router.get("/library", response_model=LibraryResponse)
async def library() -> LibraryResponse:
    driver = get_driver()
    topics = await chunks_db.all_topics()
    groups: list[LibraryGroup] = []
    for topic in topics:
        concept_ids = await chunks_db.concept_ids_by_topic(topic)
        nodes = fetch_nodes_brief(driver, concept_ids)
        groups.append(
            LibraryGroup(
                topic=topic,
                label=TOPIC_LABELS.get(topic, topic),
                count=len(nodes),
                nodes=[NodeRef(**n) for n in nodes],
            )
        )
    counts = graph_counts(driver)
    return LibraryResponse(
        groups=groups,
        total_nodes=counts["nodes"],
        total_edges=counts["edges"],
        total_topics=len(topics),
    )
