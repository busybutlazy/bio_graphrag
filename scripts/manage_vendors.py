"""Manage per-company access accounts (the ``vendors`` table).

Run inside the backend container where PYTHONPATH=/app and Postgres is reachable:

    docker compose exec backend python -m scripts.manage_vendors list
    docker compose exec backend python -m scripts.manage_vendors add \\
        --code acme --name "Acme Corp" --quota 50000 --expires 2026-08-01
    docker compose exec backend python -m scripts.manage_vendors update --code acme --quota 100000
    docker compose exec backend python -m scripts.manage_vendors disable --code acme
    docker compose exec backend python -m scripts.manage_vendors enable  --code acme

Accounts are demo-grade: the api_key is stored in plaintext. Fine for a portfolio
demo, not a production credential store.
"""

import argparse
import asyncio
import secrets
from datetime import date

import asyncpg
from app.db import vendors as vendors_db
from app.db.pool import connection


def _mask(key: str) -> str:
    return f"{key[:4]}…{key[-2:]}" if len(key) > 6 else "***"


def _parse_expires(value: str | None) -> date | None:
    if value is None:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise SystemExit(f"invalid --expires '{value}': expected YYYY-MM-DD")


async def cmd_add(args: argparse.Namespace) -> None:
    key = args.key or secrets.token_urlsafe(24)
    expires = _parse_expires(args.expires)
    async with connection() as conn:
        try:
            await conn.execute(
                """
                INSERT INTO vendors (vendor_code, name, api_key, expires_at, token_quota, active)
                VALUES ($1, $2, $3, $4, $5, true)
                """,
                args.code,
                args.name,
                key,
                expires,
                args.quota,
            )
        except asyncpg.UniqueViolationError:
            raise SystemExit(f"vendor_code '{args.code}' or that --key already exists")
    print(f"created vendor '{args.code}' ({args.name})")
    print(f"  api_key (shown once — give this to the company): {key}")
    print(f"  quota={args.quota}  expires={args.expires or 'never'}")


async def cmd_update(args: argparse.Namespace) -> None:
    sets, values = [], []
    for col, val in (
        ("name", args.name),
        ("token_quota", args.quota),
        ("api_key", args.key),
    ):
        if val is not None:
            values.append(val)
            sets.append(f"{col} = ${len(values)}")
    if args.expires is not None:
        values.append(_parse_expires(args.expires))
        sets.append(f"expires_at = ${len(values)}")
    if not sets:
        raise SystemExit("nothing to update: pass at least one of --name/--quota/--expires/--key")
    values.append(args.code)
    async with connection() as conn:
        result = await conn.execute(
            f"UPDATE vendors SET {', '.join(sets)}, updated_at = now() WHERE vendor_code = ${len(values)}",
            *values,
        )
    _require_hit(result, args.code)
    print(f"updated vendor '{args.code}'")


async def _set_active(code: str, active: bool) -> None:
    async with connection() as conn:
        result = await conn.execute(
            "UPDATE vendors SET active = $1, updated_at = now() WHERE vendor_code = $2",
            active,
            code,
        )
    _require_hit(result, code)
    print(f"vendor '{code}' {'enabled' if active else 'disabled'}")


def _require_hit(result: str, code: str) -> None:
    # asyncpg returns e.g. "UPDATE 1"; 0 rows means no such vendor_code.
    if result.endswith(" 0"):
        raise SystemExit(f"no vendor with code '{code}'")


async def cmd_list(_: argparse.Namespace) -> None:
    async with connection() as conn:
        rows = await conn.fetch(
            "SELECT vendor_code, name, api_key, expires_at, token_quota, active FROM vendors ORDER BY vendor_code"
        )
    if not rows:
        print("(no vendors)")
        return
    print(f"{'code':<20} {'name':<24} {'key':<10} {'expires':<12} {'used/quota':<16} active")
    for r in rows:
        used = await vendors_db.tokens_used(r["vendor_code"])
        expires = r["expires_at"].isoformat() if r["expires_at"] else "never"
        usage = f"{used}/{r['token_quota']}"
        print(
            f"{r['vendor_code']:<20} {r['name']:<24} {_mask(r['api_key']):<10} "
            f"{expires:<12} {usage:<16} {r['active']}"
        )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage per-company vendor accounts.")
    sub = parser.add_subparsers(dest="command", required=True)

    def quota_type(value: str) -> int:
        n = int(value)
        if n < 0:
            raise argparse.ArgumentTypeError("must be a non-negative integer (0 = no token access)")
        return n

    p_add = sub.add_parser("add", help="create a vendor account")
    p_add.add_argument("--code", required=True, help="human handle, e.g. acme")
    p_add.add_argument("--name", required=True, help="display name, e.g. 'Acme Corp'")
    p_add.add_argument("--quota", required=True, type=quota_type, help="token cap (0 = no access)")
    p_add.add_argument("--expires", help="YYYY-MM-DD; omit for no expiry")
    p_add.add_argument("--key", help="api_key; auto-generated if omitted")
    p_add.set_defaults(func=cmd_add)

    p_upd = sub.add_parser("update", help="modify a vendor account")
    p_upd.add_argument("--code", required=True)
    p_upd.add_argument("--name")
    p_upd.add_argument("--quota", type=quota_type)
    p_upd.add_argument("--expires", help="YYYY-MM-DD")
    p_upd.add_argument("--key")
    p_upd.set_defaults(func=cmd_update)

    p_dis = sub.add_parser("disable", help="deactivate a vendor")
    p_dis.add_argument("--code", required=True)
    p_dis.set_defaults(func=lambda a: _set_active(a.code, False))

    p_en = sub.add_parser("enable", help="reactivate a vendor")
    p_en.add_argument("--code", required=True)
    p_en.set_defaults(func=lambda a: _set_active(a.code, True))

    p_list = sub.add_parser("list", help="list all vendors")
    p_list.set_defaults(func=cmd_list)

    return parser


def main() -> None:
    args = _build_parser().parse_args()
    asyncio.run(args.func(args))


if __name__ == "__main__":
    main()
