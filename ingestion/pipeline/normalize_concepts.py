VALID_NODE_TYPES = {
    "Concept",
    "System",
    "Process",
    "Structure",
    "Molecule",
    "Hormone",
    "Receptor",
    "PhysiologicalVariable",
    "RegulatoryEffect",
    "Interaction",
    "FeedbackLoop",
    "Enzyme",
    "Disease",
    "Experiment",
    "Misconception",
}

VALID_RELATIONSHIP_TYPES = {
    "PART_OF",
    "SECRETES",
    "SECRETED_BY",
    "BINDS_TO",
    "TARGETS",
    "HAS_EFFECT",
    "ON_VARIABLE",
    "INCREASES",
    "DECREASES",
    "REGULATES_SECRETION_OF",
    "PARTICIPATES_IN",
    "USES_EFFECT",
    "CATALYZES",
    "PREREQUISITE_OF",
    "CAUSES",
    "EVIDENCED_BY",
    "COMMONLY_CONFUSED_WITH",
}

REQUIRED_NODE_FIELDS = {"id", "type", "label", "status", "description"}
REQUIRED_EDGE_FIELDS = {"id", "type", "source", "target", "status"}

# Node types that anchor a reviewable *statement*: a RegulatoryEffect or an Interaction is the hub
# a whole biological claim hangs off. Used by ``group_statements`` to split one extraction output
# into one review group per statement, and mirrored by the Schema gate, which special-cases exactly
# these two types when checking pattern completeness
# (``backend/app/graph/engineer_gate.py::_pattern_check``). A drift guard in
# ``backend/tests/unit/test_engineer_gate.py`` pins the two sets in agreement — backend may import
# ingestion, never the reverse, so this constant lives here.
PATTERN_ANCHOR_TYPES = {"RegulatoryEffect", "Interaction"}


class ValidationError(ValueError):
    pass


def validate_nodes(nodes: list[dict]) -> None:
    ids = [n["id"] for n in nodes]
    if len(ids) != len(set(ids)):
        raise ValidationError("duplicate node ids")

    for node in nodes:
        missing = REQUIRED_NODE_FIELDS - node.keys()
        if missing:
            raise ValidationError(f"node {node.get('id')} missing fields: {missing}")
        if node["type"] not in VALID_NODE_TYPES:
            raise ValidationError(f"node {node['id']} has invalid type {node['type']}")


def validate_edges(nodes: list[dict], edges: list[dict]) -> None:
    node_ids = {n["id"] for n in nodes}
    edge_ids = [e["id"] for e in edges]
    if len(edge_ids) != len(set(edge_ids)):
        raise ValidationError("duplicate edge ids")

    for edge in edges:
        missing = REQUIRED_EDGE_FIELDS - edge.keys()
        if missing:
            raise ValidationError(f"edge {edge.get('id')} missing fields: {missing}")
        if edge["type"] not in VALID_RELATIONSHIP_TYPES:
            raise ValidationError(f"edge {edge['id']} has invalid type {edge['type']}")
        if edge["source"] not in node_ids:
            raise ValidationError(f"edge {edge['id']} source {edge['source']} does not exist")
        if edge["target"] not in node_ids:
            raise ValidationError(f"edge {edge['id']} target {edge['target']} does not exist")
