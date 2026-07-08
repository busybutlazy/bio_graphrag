import hashlib
import os

EMBEDDING_DIM = 128


def _deterministic_embedding(text: str, dim: int = EMBEDDING_DIM) -> list[float]:
    vector: list[float] = []
    counter = 0
    while len(vector) < dim:
        digest = hashlib.sha256(f"{text}:{counter}".encode("utf-8")).digest()
        vector.extend(b / 255.0 for b in digest)
        counter += 1
    return vector[:dim]


def _embed_with_openai(text: str) -> tuple[list[float], int]:
    from openai import OpenAI

    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    response = client.embeddings.create(model="text-embedding-3-small", input=text)
    return response.data[0].embedding, response.usage.total_tokens


def embed_text(text: str) -> tuple[list[float], int]:
    """Return ``(vector, embedding_tokens)``; tokens is 0 for the offline path.

    ``embedding_tokens`` is a plain int (not app.llm.TokenUsage) so this
    ingestion module stays free of any backend-app import.
    """
    provider = os.getenv("LLM_PROVIDER", "openai")
    api_key = os.getenv("OPENAI_API_KEY", "")
    if provider == "openai" and api_key:
        return _embed_with_openai(text)
    return _deterministic_embedding(text), 0


def embed_chunks(chunks: list[dict]) -> dict[str, list[float]]:
    # Ingestion cost is not attributed per-vendor, so drop the token count here.
    return {chunk["chunk_id"]: embed_text(chunk["content"])[0] for chunk in chunks}
