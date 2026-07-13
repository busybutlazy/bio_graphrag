import json
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]

# Public demo fallback — committed to git, always present.
DATA_DIR = _REPO_ROOT / "data" / "sample"

# Real exported knowledge — gitignored, takes priority when present.
# Populated by `make export-seed`; copy manually when switching machines.
_SEED_DIR = _REPO_ROOT / "data" / "seed"


def _active_seed_dir() -> Path:
    """Return data/seed/ if it contains real exported data, else data/sample/."""
    if (_SEED_DIR / "biology_sample_concepts.json").exists():
        return _SEED_DIR
    return DATA_DIR


def load_graph_source() -> tuple[list[dict], list[dict]]:
    d = _active_seed_dir()
    nodes = json.loads((d / "biology_sample_concepts.json").read_text())
    edges = json.loads((d / "biology_sample_edges.json").read_text())
    return nodes, edges


def load_chunk_source() -> tuple[list[dict], list[dict]]:
    d = _active_seed_dir()
    documents = json.loads((d / "biology_sample_documents.json").read_text())
    chunks = json.loads((d / "biology_sample_chunks.json").read_text())
    return documents, chunks
