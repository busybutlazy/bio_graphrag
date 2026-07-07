REQUIRED_CHUNK_FIELDS = {"chunk_id", "doc_id", "content", "concept_ids", "topic", "grade_level", "source_type"}


class ChunkValidationError(ValueError):
    pass


def build(chunks: list[dict], nodes: list[dict]) -> list[dict]:
    node_ids = {n["id"] for n in nodes}
    chunk_ids = [c["chunk_id"] for c in chunks]
    if len(chunk_ids) != len(set(chunk_ids)):
        raise ChunkValidationError("duplicate chunk ids")

    for chunk in chunks:
        missing = REQUIRED_CHUNK_FIELDS - chunk.keys()
        if missing:
            raise ChunkValidationError(f"chunk {chunk.get('chunk_id')} missing fields: {missing}")
        unknown = [cid for cid in chunk["concept_ids"] if cid not in node_ids]
        if unknown:
            raise ChunkValidationError(f"chunk {chunk['chunk_id']} references unknown concept_ids: {unknown}")

    return chunks
