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


async def get_vendor_with_usage(api_key: str) -> tuple[Vendor, int] | None:
    """Fetch the vendor and its cumulative token usage in one round-trip.

    Returns ``(vendor, tokens_used)`` or ``None`` if the key is unknown. Folding
    the usage sum into the same query keeps ``require_vendor`` to a single DB hit.
    """
    async with connection() as conn:
        row = await conn.fetchrow(
            """
            SELECT v.vendor_code, v.name, v.api_key, v.expires_at, v.token_quota, v.active,
                   COALESCE(
                       (SELECT SUM(u.tokens_used) FROM vendor_usage u
                        WHERE u.vendor_code = v.vendor_code), 0
                   ) AS used
            FROM vendors v WHERE v.api_key = $1
            """,
            api_key,
        )
    if row is None:
        return None
    vendor = Vendor(
        vendor_code=row["vendor_code"],
        name=row["name"],
        api_key=row["api_key"],
        expires_at=row["expires_at"],
        token_quota=row["token_quota"],
        active=row["active"],
    )
    return vendor, row["used"]


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
