from qdrant_client import QdrantClient

from app.core.config import settings


def check_qdrant() -> tuple[bool, str | None]:
    try:
        client = QdrantClient(url=settings.qdrant_url, timeout=5)
        client.get_collections()
        return True, None
    except Exception as exc:
        return False, str(exc)
