"""Named API-key auth for the /admin endpoints.

Keys are configured as a comma-separated ``vendor:key`` list in
``settings.admin_api_keys`` (e.g. ``"acme:key1,globex:key2"``). A request must
send a matching key in the ``X-API-Key`` header; the resolved vendor name is
returned so handlers/logs can attribute the action.

When no keys are configured the guard is a no-op — the local Docker demo and the
test suite run without credentials. Configure keys in any exposed deployment.
"""

from fastapi import Header, HTTPException

from app.core.config import settings


def parse_api_keys(raw: str) -> dict[str, str]:
    """Parse a ``vendor:key,vendor:key`` string into ``{key: vendor}``."""
    keys: dict[str, str] = {}
    for pair in raw.split(","):
        pair = pair.strip()
        if not pair:
            continue
        vendor, sep, key = pair.partition(":")
        if sep and key.strip():
            keys[key.strip()] = vendor.strip()
    return keys


async def require_admin(x_api_key: str | None = Header(default=None)) -> str:
    """FastAPI dependency: allow the request and return the caller's vendor name.

    Returns ``"anonymous"`` when auth is disabled (no keys configured).
    """
    keys = parse_api_keys(settings.admin_api_keys)
    if not keys:
        return "anonymous"
    if x_api_key is None or x_api_key not in keys:
        raise HTTPException(status_code=401, detail="invalid or missing API key")
    return keys[x_api_key]
