import pytest

from ingestion.pipeline import build_chunks, parse_source


def test_sample_chunks_concept_ids_resolve_to_real_nodes():
    nodes, _ = parse_source.load_graph_source()
    _, chunks = parse_source.load_chunk_source()
    result = build_chunks.build(chunks, nodes)
    assert len(result) == len(chunks)


def test_build_rejects_unknown_concept_id():
    nodes = [
        {
            "id": "hormone:x",
            "type": "Hormone",
            "label": "X",
            "status": "approved",
            "description": "test",
        }
    ]
    chunks = [
        {
            "chunk_id": "chunk:test:001",
            "doc_id": "doc:test:001",
            "content": "test",
            "concept_ids": ["hormone:does_not_exist"],
            "topic": "test",
            "grade_level": "高二",
            "source_type": "sample",
        }
    ]
    with pytest.raises(build_chunks.ChunkValidationError):
        build_chunks.build(chunks, nodes)


def test_build_rejects_missing_field():
    nodes = [
        {
            "id": "hormone:x",
            "type": "Hormone",
            "label": "X",
            "status": "approved",
            "description": "test",
        }
    ]
    chunks = [{"chunk_id": "chunk:test:001", "doc_id": "doc:test:001"}]
    with pytest.raises(build_chunks.ChunkValidationError):
        build_chunks.build(chunks, nodes)
