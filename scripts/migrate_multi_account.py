"""One-shot multi-account DB migration (B.1).

Idempotent-ish, safe-by-default: it backs the live SQLite file up before touching it, then

  1. drops + recreates ``positions`` as a holdings snapshot (empty — no backfill;
     ``sync_portfolio_from_cdp`` is the writer),
  2. ``ALTER TABLE orders ADD COLUMN`` the new additive multi-account columns,
  3. creates ``broker_accounts``,
  4. verifies ``orders`` and ``session_logs`` row counts are unchanged.

Run from the repo root::

    .venv/bin/python scripts/migrate_multi_account.py

The function ``run_migration(db_path, do_backup=True)`` is importable so the test suite can
exercise the exact same code path against a throwaway copy of an old-schema DB.
"""
from __future__ import annotations

import asyncio
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.db.models import Base

#: (column, SQLite type) appended to ``orders``. Existing rows keep NULL (account_no/broker/
#: matched_price) or 0 (matched_volume/cancel_volume) via the server DEFAULT.
NEW_ORDER_COLUMNS = [
    ("account_no", "VARCHAR(32)"),
    ("broker", "VARCHAR(32)"),
    ("matched_volume", "INTEGER DEFAULT 0"),
    ("matched_price", "REAL"),
    ("cancel_volume", "INTEGER DEFAULT 0"),
]


def db_path_from_url(url: str) -> Path:
    """Resolve the SQLite file path from a ``sqlite+aiosqlite:///...`` URL."""
    marker = "sqlite+aiosqlite:///"
    if url.startswith(marker):
        return Path(url[len(marker):])
    # Fallback: strip any other sqlite driver prefix.
    if ":///" in url:
        return Path(url.split(":///", 1)[1])
    return Path(url)


def backup_db(db_path: Path) -> Path:
    """Copy ``db_path`` to a timestamped ``.bak`` sibling. Returns the backup path."""
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    bak = db_path.with_name(f"{db_path.name}.bak.{stamp}")
    shutil.copy2(db_path, bak)
    return bak


async def _count(conn, table: str) -> int:
    res = await conn.execute(text(f"SELECT COUNT(*) FROM {table}"))
    return int(res.scalar_one())


async def run_migration(db_path: Path, do_backup: bool = True) -> dict:
    """Apply the multi-account migration to ``db_path``. Returns an audit dict.

    Raises AssertionError if ``orders`` or ``session_logs`` row counts change.
    """
    if not db_path.exists():
        raise FileNotFoundError(f"database not found: {db_path}")

    backup_path: Optional[Path] = backup_db(db_path) if do_backup else None

    engine = create_async_engine(
        f"sqlite+aiosqlite:///{db_path}",
        connect_args={"check_same_thread": False},
    )

    try:
        async with engine.begin() as conn:
            orders_before = await _count(conn, "orders")
            logs_before = await _count(conn, "session_logs")

            # 1. positions -> holdings snapshot (drop + recreate empty, no backfill).
            await conn.execute(text("DROP TABLE IF EXISTS positions"))
            # create_all re-creates positions (new schema) and broker_accounts (new table);
            # every other existing table is left untouched (checkfirst=True).
            await conn.run_sync(Base.metadata.create_all)

            # 2. orders -> additive multi-account columns.
            for col, col_type in NEW_ORDER_COLUMNS:
                try:
                    await conn.execute(text(f"ALTER TABLE orders ADD COLUMN {col} {col_type}"))
                except Exception:
                    # Column already present (re-run) — idempotent.
                    pass

            orders_after = await _count(conn, "orders")
            logs_after = await _count(conn, "session_logs")
            positions_after = await _count(conn, "positions")
            accounts_after = await _count(conn, "broker_accounts")
    finally:
        await engine.dispose()

    result = {
        "db_path": str(db_path),
        "backup_path": str(backup_path) if backup_path else None,
        "orders_before": orders_before,
        "orders_after": orders_after,
        "session_logs_before": logs_before,
        "session_logs_after": logs_after,
        "positions_after": positions_after,
        "broker_accounts_after": accounts_after,
    }

    assert orders_before == orders_after, (
        f"orders row count changed during migration: {orders_before} -> {orders_after}"
    )
    assert logs_before == logs_after, (
        f"session_logs row count changed during migration: {logs_before} -> {logs_after}"
    )
    return result


async def _main() -> int:
    from app.core.config import settings

    db_path = db_path_from_url(settings.DATABASE_URL)
    print(f"Migrating {db_path} ...")
    result = await run_migration(db_path, do_backup=True)
    print("Migration OK:")
    for key, value in result.items():
        print(f"  {key}: {value}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(_main()))
    except Exception as exc:  # noqa: BLE001 - CLI needs a clean, non-traceback failure
        print(f"Migration FAILED: {exc}", file=sys.stderr)
        sys.exit(1)
