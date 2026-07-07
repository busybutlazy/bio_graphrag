from pydantic import BaseModel


class NodeRef(BaseModel):
    id: str
    label: str
    type: str


class RelationshipRef(BaseModel):
    source: str
    relation: str
    target: str


class NeighborsResponse(BaseModel):
    center_node: NodeRef
    nodes: list[NodeRef]
    edges: list[RelationshipRef]
    depth: int
