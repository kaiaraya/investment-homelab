"""B.1 multi-account DB redesign — unit tests.

Covers:
  * composite uniqueness of ``positions(account_no, symbol)``,
  * UPSERT semantics for ``broker_accounts`` and ``positions`` (sqlite ON CONFLICT DO UPDATE),
  * the one-shot migration preserving ``orders`` / ``session_logs`` while dropping+recreating
    ``positions`` empty and creating ``broker_accounts``.
"""
import sqlite3
from pathlib import Path

import pytest
from sqlalchemy import insert, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import IntegrityError

from app.db.models import BrokerAccount, Order, Position, SessionLog
from scripts.migrate_multi_account import run_migration

# ── Old (pre-B.1) schema, matching the live investment_homelab.db at migration time ──────
OLD_SCHEMA_DDL = [
    """
    CREATE TABLE sbl_borrow_lots (
        lot_id VARCHAR(64) NOT NULL,
        broker_tx_id VARCHAR(64),
        symbol VARCHAR(16) NOT NULL,
        borrow_qty INTEGER NOT NULL,
        remaining_qty INTEGER NOT NULL,
        borrow_price FLOAT,
        borrow_fee_rate FLOAT NOT NULL,
        borrow_date DATE NOT NULL,
        return_date DATE,
        status VARCHAR(32) NOT NULL,
        ex_dividend_date DATE,
        expiry_date DATE,
        PRIMARY KEY (lot_id)
    )
    """,
    """
    CREATE TABLE positions (
        symbol VARCHAR(16) NOT NULL,
        position_type VARCHAR(16) NOT NULL,
        volume INTEGER NOT NULL,
        avg_cost FLOAT NOT NULL,
        current_price FLOAT,
        unrealized_pnl FLOAT,
        associated_sbl_lot_id VARCHAR(64),
        opened_at DATETIME NOT NULL,
        updated_at DATETIME NOT NULL,
        take_profit_price REAL,
        stop_loss_price REAL,
        prior_close_price REAL,
        is_sbl_pending_return BOOLEAN DEFAULT 0,
        PRIMARY KEY (symbol),
        FOREIGN KEY(associated_sbl_lot_id) REFERENCES sbl_borrow_lots (lot_id)
    )
    """,
    """
    CREATE TABLE orders (
        order_id VARCHAR(64) NOT NULL,
        broker_order_no VARCHAR(64),
        symbol VARCHAR(16) NOT NULL,
        side VARCHAR(16) NOT NULL,
        volume INTEGER NOT NULL,
        price FLOAT NOT NULL,
        status VARCHAR(32) NOT NULL,
        error_message TEXT,
        source VARCHAR(32) NOT NULL,
        created_at DATETIME NOT NULL,
        updated_at DATETIME NOT NULL,
        is_negotiated BOOLEAN DEFAULT 0,
        original_price REAL,
        negotiated_price REAL,
        position VARCHAR(16),
        PRIMARY KEY (order_id)
    )
    """,
    """
    CREATE TABLE session_logs (
        id INTEGER NOT NULL,
        event_type VARCHAR(64) NOT NULL,
        details TEXT,
        created_at DATETIME NOT NULL,
        PRIMARY KEY (id)
    )
    """,
]


def build_old_db(path: Path) -> None:
    """Create an old-schema DB with seed rows (1 sbl lot, 1 position, 2 orders, 3 logs)."""
    conn = sqlite3.connect(path)
    try:
        for stmt in OLD_SCHEMA_DDL:
            conn.execute(stmt)
        conn.execute(
            "INSERT INTO sbl_borrow_lots "
            "(lot_id, broker_tx_id, symbol, borrow_qty, remaining_qty, borrow_fee_rate, borrow_date, status) "
            "VALUES ('LOT-1', 'TX-1', 'AP', 2000, 2000, 3.5, '2026-10-15', 'ACTIVE')"
        )
        conn.execute(
            "INSERT INTO positions "
            "(symbol, position_type, volume, avg_cost, current_price, unrealized_pnl, opened_at, updated_at) "
            "VALUES ('AP', 'SHORT', 2000, 8.10, 8.15, -100.0, '2026-10-15 09:00:00', '2026-10-15 09:00:00')"
        )
        for i in (1, 2):
            conn.execute(
                "INSERT INTO orders "
                "(order_id, symbol, side, volume, price, status, source, created_at, updated_at) "
                f"VALUES ('ORD-{i}', 'AP', 'BUY', 100, 8.0, 'OPEN', 'api', '2026-10-15 09:00:00', '2026-10-15 09:00:00')"
            )
        for i in range(3):
            conn.execute(
                "INSERT INTO session_logs (event_type, details, created_at) "
                f"VALUES ('TEST', 'log {i}', '2026-10-15 09:00:00')"
            )
        conn.commit()
    finally:
        conn.close()


# ── Composite uniqueness + UPSERT (new schema, via test_homelab.db autouse fixture) ──────

@pytest.mark.asyncio
async def test_positions_composite_uniqueness(prepare_test_db):
    from tests.conftest import TestingSessionLocal

    async with TestingSessionLocal() as session:
        session.add(Position(
            account_no="3024959", symbol="AP", position_type="SHORT",
            volume=2000, avg_cost=8.10,
        ))
        session.add(Position(
            account_no="7055938", symbol="AP", position_type="LONG",
            volume=500, avg_cost=8.05,
        ))
        await session.commit()

        # Same symbol, two accounts -> two rows.
        rows = (await session.execute(select(Position).order_by(Position.account_no))).scalars().all()
        assert len(rows) == 2
        assert {(r.account_no, r.symbol) for r in rows} == {("3024959", "AP"), ("7055938", "AP")}

        # Duplicate composite key -> rejected at the DB constraint (raw INSERT bypasses
        # the ORM identity map so we actually exercise the UNIQUE/PK constraint).
        with pytest.raises(IntegrityError):
            await session.execute(
                insert(Position).values(
                    account_no="3024959", symbol="AP", position_type="LONG",
                    volume=1, avg_cost=0.0,
                )
            )


@pytest.mark.asyncio
async def test_broker_accounts_upsert(prepare_test_db):
    from tests.conftest import TestingSessionLocal

    async with TestingSessionLocal() as session:
        def stmt(**values):
            ins = sqlite_insert(BrokerAccount).values(**values)
            return ins.on_conflict_do_update(
                index_elements=[BrokerAccount.account_no],
                set_={
                    "broker": ins.excluded.broker,
                    "account_type": ins.excluded.account_type,
                    "line_available": ins.excluded.line_available,
                },
            )

        await session.execute(stmt(
            account_no="3024959", broker="KRUNGSRI",
            account_type="CREDIT_BALANCE", line_available=1_000_000.0,
        ))
        await session.execute(stmt(
            account_no="3024959", broker="KRUNGSRI",
            account_type="CREDIT_BALANCE", line_available=950_000.0,
        ))
        await session.commit()

        rows = (await session.execute(select(BrokerAccount))).scalars().all()
        assert len(rows) == 1
        assert rows[0].account_no == "3024959"
        assert rows[0].line_available == 950_000.0


@pytest.mark.asyncio
async def test_positions_upsert(prepare_test_db):
    from tests.conftest import TestingSessionLocal

    async with TestingSessionLocal() as session:
        def stmt(**values):
            ins = sqlite_insert(Position).values(**values)
            return ins.on_conflict_do_update(
                index_elements=["account_no", "symbol"],
                set_={
                    "volume": ins.excluded.volume,
                    "current_price": ins.excluded.current_price,
                    "market_value": ins.excluded.market_value,
                },
            )

        await session.execute(stmt(
            account_no="3024959", symbol="AP", position_type="SHORT",
            volume=2000, avg_cost=8.10, current_price=8.15, market_value=16_300.0,
        ))
        await session.execute(stmt(
            account_no="3024959", symbol="AP", position_type="SHORT",
            volume=1500, avg_cost=8.10, current_price=8.20, market_value=12_300.0,
        ))
        await session.commit()

        rows = (await session.execute(select(Position))).scalars().all()
        assert len(rows) == 1
        assert rows[0].account_no == "3024959"
        assert rows[0].symbol == "AP"
        assert rows[0].volume == 1500
        assert rows[0].market_value == 12_300.0


# ── Migration on a throwaway old-schema copy ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_migration_preserves_orders_and_session_logs(tmp_path):
    db = tmp_path / "old_homelab.db"
    build_old_db(db)

    result = await run_migration(db, do_backup=True)

    # Row counts from the migration's own audit.
    assert result["orders_before"] == result["orders_after"] == 2
    assert result["session_logs_before"] == result["session_logs_after"] == 3
    assert result["positions_after"] == 0
    assert result["broker_accounts_after"] == 0

    # Re-read the migrated DB from disk.
    conn = sqlite3.connect(db)
    try:
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert "broker_accounts" in tables

        assert conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0] == 2
        assert conn.execute("SELECT COUNT(*) FROM session_logs").fetchone()[0] == 3
        assert conn.execute("SELECT COUNT(*) FROM positions").fetchone()[0] == 0

        order_cols = {r[1] for r in conn.execute("PRAGMA table_info(orders)")}
        assert {"account_no", "broker", "matched_volume", "matched_price", "cancel_volume"} <= order_cols

        pos_cols = {r[1] for r in conn.execute("PRAGMA table_info(positions)")}
        assert {"account_no", "available_volume", "market_value", "unrealized_pnl_pct"} <= pos_cols

        # Order content intact, not just the count.
        order_ids = {r[0] for r in conn.execute("SELECT order_id FROM orders")}
        assert order_ids == {"ORD-1", "ORD-2"}
    finally:
        conn.close()

    # Backup is a byte-for-byte copy of the pre-migration DB (old positions still present).
    backup = Path(result["backup_path"])
    assert backup.exists()
    bconn = sqlite3.connect(backup)
    try:
        assert bconn.execute("SELECT COUNT(*) FROM positions").fetchone()[0] == 1
        assert bconn.execute("SELECT COUNT(*) FROM orders").fetchone()[0] == 2
    finally:
        bconn.close()

    # Idempotent: a second run keeps orders/session_logs intact and positions empty.
    result2 = await run_migration(db, do_backup=False)
    assert result2["orders_after"] == 2
    assert result2["session_logs_after"] == 3
    assert result2["positions_after"] == 0


@pytest.mark.asyncio
async def test_migration_missing_db_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        await run_migration(tmp_path / "does_not_exist.db", do_backup=False)
