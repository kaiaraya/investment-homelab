import logging
from sqlalchemy import text
from app.db.session import engine, engine_click2win
from app.db.models import Base

logger = logging.getLogger(__name__)


async def init_db() -> None:
    """Create database tables if they do not exist, and safely add new columns for both primary and click2win databases."""
    logger.info("Initializing SQLite database tables...")
    for eng, name in [(engine, "Primary (Krungsri TradeMan)"), (engine_click2win, "Sandbox (Click2Win)")]:
        logger.info(f"Setting up database schema for {name}...")
        async with eng.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

            # Migrations for Phase 3 columns
            alter_statements = [
                ("positions", "take_profit_price", "REAL"),
                ("positions", "stop_loss_price", "REAL"),
                ("positions", "prior_close_price", "REAL"),
                ("positions", "is_sbl_pending_return", "BOOLEAN DEFAULT 0"),
                ("sbl_borrow_lots", "ex_dividend_date", "DATE"),
                ("sbl_borrow_lots", "expiry_date", "DATE"),
                ("orders", "is_negotiated", "BOOLEAN DEFAULT 0"),
                ("orders", "original_price", "REAL"),
                ("orders", "negotiated_price", "REAL"),
                ("orders", "position", "VARCHAR(16)"),
            ]
            for table, col, col_type in alter_statements:
                try:
                    await conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {col_type}"))
                except Exception:
                    # Column likely already exists
                    pass

    logger.info("All database tables and columns initialized successfully.")


