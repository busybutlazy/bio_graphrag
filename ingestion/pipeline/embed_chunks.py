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


def _embed_with_openai(text: str) -> list[float]:
    from openai import OpenAI

    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    response = client.embeddings.create(model="text-embedding-3-small", input=text)
    return response.data[0].embedding


def embed_text(text: str) -> list[float]:
    provider = os.getenv("LLM_PROVIDER", "openai")
    api_key = os.getenv("OPENAI_API_KEY", "")
    if provider == "openai" and api_key:
        return _embed_with_openai(text)
    return _deterministic_embedding(text)


def embed_chunks(chunks: list[dict]) -> dict[str, list[float]]:
    return {chunk["chunk_id"]: embed_text(chunk["content"]) for chunk in chunks}
