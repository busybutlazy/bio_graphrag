import json
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "sample"


def load_graph_source() -> tuple[list[dict], list[dict]]:
    nodes = json.loads((DATA_DIR / "biology_sample_concepts.json").read_text())
    edges = json.loads((DATA_DIR / "biology_sample_edges.json").read_text())
    return nodes, edges


def load_chunk_source() -> tuple[list[dict], list[dict]]:
    documents = json.loads((DATA_DIR / "biology_sample_documents.json").read_text())
    chunks = json.loads((DATA_DIR / "biology_sample_chunks.json").read_text())
    return documents, chunks
