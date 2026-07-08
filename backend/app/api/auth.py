"""Named API-key auth for the /admin endpoints.

Keys are configured as a comma-separated ``vendor:key`` list in
``settings.admin_api_keys`` (e.g. ``"acme:key1,globex:key2"``). A request must
send a matching key in the ``X-API-Key`` header; the resolved vendor name is
returned so handlers/logs can attribute the action.

When no keys are configured the guard is a no-op — the local Docker demo and the
test suite run without credentials. Configure keys in any exposed deployment.
"""

from datetime import date

from fastapi import Header, HTTPException

from app.api.errors import APIError
from app.core.config import settings
from app.db import vendors as vendors_db


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


async def require_vendor(x_api_key: str | None = Header(default=None)) -> vendors_db.Vendor:
    """Gate the token-spending endpoints on a valid company account.

    Closed by default: with no account (or an unknown key) every request is
    rejected — there is no "open when unconfigured" fallback. Precedence:
      no/unknown key -> 401 login_required
      known but inactive -> 403 account_disabled
      expired -> 403 account_expired
      over quota -> 403 quota_exceeded  (token_quota 0 = no token access)
    """
    if not x_api_key:
        raise APIError(401, "login_required", "請先登入公司帳號以使用問答功能。")
    found = await vendors_db.get_vendor_with_usage(x_api_key)
    if found is None:
        raise APIError(401, "login_required", "請先登入公司帳號以使用問答功能。")
    vendor, used = found
    if not vendor.active:
        raise APIError(403, "account_disabled", "此帳號已停用,請聯絡管理員。")
    if vendor.expires_at is not None and vendor.expires_at < date.today():
        raise APIError(403, "account_expired", "此帳號已到期,請聯絡管理員。")
    if used >= vendor.token_quota:
        raise APIError(403, "quota_exceeded", "本公司 token 額度已用盡,請聯絡管理員。")
    return vendor
