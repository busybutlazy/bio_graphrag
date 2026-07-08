"""Vendor accounts + token-usage tally (Postgres).

Accounts live in the ``vendors`` table (hand-maintained via
``backend/scripts/manage_vendors.py``); cumulative token spend is summed from
``vendor_usage``. Usage is keyed by ``vendor_code`` (the human handle), never by
the secret api_key.
"""

from dataclasses import dataclass
from datetime import date

from app.db.pool import connection


@dataclass(frozen=True)
class Vendor:
    vendor_code: str
    name: str
    api_key: str
    expires_at: date | None
    token_quota: int
    active: bool


async def get_vendor(api_key: str) -> Vendor | None:
    async with connection() as conn:
        row = await conn.fetchrow(
            """
            SELECT vendor_code, name, api_key, expires_at, token_quota, active
            FROM vendors WHERE api_key = $1
            """,
            api_key,
        )
    if row is None:
        return None
    return Vendor(
        vendor_code=row["vendor_code"],
        name=row["name"],
        api_key=row["api_key"],
        expires_at=row["expires_at"],
        token_quota=row["token_quota"],
        active=row["active"],
    )


async def tokens_used(vendor_code: str) -> int:
    async with connection() as conn:
        return await conn.fetchval(
            "SELECT COALESCE(SUM(tokens_used), 0) FROM vendor_usage WHERE vendor_code = $1",
            vendor_code,
        )


async def record_usage(vendor_code: str, tokens: int, endpoint: str) -> None:
    async with connection() as conn:
        await conn.execute(
            "INSERT INTO vendor_usage (vendor_code, tokens_used, endpoint) VALUES ($1, $2, $3)",
            vendor_code,
            tokens,
            endpoint,
        )
