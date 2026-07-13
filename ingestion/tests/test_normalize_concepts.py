import pytest

from ingestion.pipeline import normalize_concepts, parse_source


def test_sample_nodes_and_edges_are_valid():
    nodes, edges = parse_source.load_graph_source()
    normalize_concepts.validate_nodes(nodes)
    normalize_concepts.validate_edges(nodes, edges)


def test_validate_nodes_rejects_missing_field():
    nodes = [
        {"id": "hormone:x", "type": "Hormone", "label": "X", "status": "approved"}
    ]  # no description
    with pytest.raises(normalize_concepts.ValidationError):
        normalize_concepts.validate_nodes(nodes)


def test_validate_nodes_rejects_unknown_type():
    nodes = [
        {
            "id": "hormone:x",
            "type": "NotARealType",
            "label": "X",
            "status": "approved",
            "description": "test",
        }
    ]
    with pytest.raises(normalize_concepts.ValidationError):
        normalize_concepts.validate_nodes(nodes)


def test_validate_edges_rejects_dangling_reference():
    nodes = [
        {
            "id": "hormone:x",
            "type": "Hormone",
            "label": "X",
            "status": "approved",
            "description": "test",
        }
    ]
    edges = [
        {
            "id": "edge:x_targets_y",
            "type": "TARGETS",
            "source": "hormone:x",
            "target": "structure:does_not_exist",
            "status": "approved",
        }
    ]
    with pytest.raises(normalize_concepts.ValidationError):
        normalize_concepts.validate_edges(nodes, edges)
