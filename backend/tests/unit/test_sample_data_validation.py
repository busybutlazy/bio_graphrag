from app.graph.seed_loader import load_sample_data

VALID_NODE_TYPES = {
    "Concept", "System", "Process", "Structure", "Molecule",
    "Hormone", "Receptor", "PhysiologicalVariable", "RegulatoryEffect",
    "Interaction", "FeedbackLoop", "Enzyme", "Disease", "Experiment",
    "Misconception",
}

VALID_RELATIONSHIP_TYPES = {
    "PART_OF", "SECRETES", "SECRETED_BY", "BINDS_TO", "TARGETS",
    "HAS_EFFECT", "ON_VARIABLE", "INCREASES", "DECREASES",
    "REGULATES_SECRETION_OF", "PARTICIPATES_IN", "USES_EFFECT",
    "CATALYZES", "PREREQUISITE_OF", "CAUSES", "EVIDENCED_BY",
    "COMMONLY_CONFUSED_WITH",
}

REQUIRED_NODE_FIELDS = {"id", "type", "label", "status", "description"}
REQUIRED_EDGE_FIELDS = {"id", "type", "source", "target", "status"}


def test_nodes_have_required_fields_and_valid_types():
    nodes, _ = load_sample_data()
    ids = [n["id"] for n in nodes]
    assert len(ids) == len(set(ids)), "duplicate node ids"

    for node in nodes:
        missing = REQUIRED_NODE_FIELDS - node.keys()
        assert not missing, f"{node.get('id')} missing fields: {missing}"
        assert node["type"] in VALID_NODE_TYPES, f"{node['id']} has invalid type {node['type']}"


def test_edges_have_required_fields_and_reference_existing_nodes():
    nodes, edges = load_sample_data()
    node_ids = {n["id"] for n in nodes}
    edge_ids = [e["id"] for e in edges]
    assert len(edge_ids) == len(set(edge_ids)), "duplicate edge ids"

    for edge in edges:
        missing = REQUIRED_EDGE_FIELDS - edge.keys()
        assert not missing, f"{edge.get('id')} missing fields: {missing}"
        assert edge["type"] in VALID_RELATIONSHIP_TYPES, f"{edge['id']} has invalid type {edge['type']}"
        assert edge["source"] in node_ids, f"{edge['id']} source {edge['source']} does not exist"
        assert edge["target"] in node_ids, f"{edge['id']} target {edge['target']} does not exist"
