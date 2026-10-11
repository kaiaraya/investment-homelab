from datetime import datetime, date
from typing import Optional
from sqlalchemy import (
    String,
    Integer,
    Float,
    Boolean,
    DateTime,
    Date,
    ForeignKey,
    Text,
    func
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Order(Base):
    """
    Table recording trade orders and lifecycle statuses.
    Status transitions: PENDING -> SUBMITTED -> FILLED / REJECTED / CANCELLED / FAILED / CARRY_OVER_PENDING / EXPIRED_EOD
    """
    __tablename__ = "orders"

    order_id: Mapped[str] = mapped_column(String(64), primary_key=True, index=True)
    broker_order_no: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    symbol: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    side: Mapped[str] = mapped_column(String(16), nullable=False)  # BUY, SELL, SHORT, COVER, LONG
    position: Mapped[Optional[str]] = mapped_column(String(16), nullable=True, default=None)  # OPEN, CLOSE, AUTO
    volume: Mapped[int] = mapped_column(Integer, nullable=False)
    price: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="PENDING", index=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(String(32), default="api")
    is_negotiated: Mapped[bool] = mapped_column(Boolean, default=False)
    original_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    negotiated_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)


class SBLBorrowLot(Base):
    """
    Table tracking Securities Borrowing and Lending (SBL) lots and interest.
    """
    __tablename__ = "sbl_borrow_lots"

    lot_id: Mapped[str] = mapped_column(String(64), primary_key=True, index=True)
    broker_tx_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)  # e.g. 8493414
    symbol: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    borrow_qty: Mapped[int] = mapped_column(Integer, nullable=False)
    remaining_qty: Mapped[int] = mapped_column(Integer, nullable=False)
    borrow_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    borrow_fee_rate: Mapped[float] = mapped_column(Float, default=3.50)  # % p.a.
    borrow_date: Mapped[date] = mapped_column(Date, nullable=False)
    return_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    ex_dividend_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    expiry_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="ACTIVE")  # ACTIVE, PARTIAL_RETURNED, FULLY_RETURNED, HELD_UNMATCHED

    positions: Mapped[list["Position"]] = relationship("Position", back_populates="sbl_lot")


class Position(Base):
    """
    Table tracking currently open portfolio positions (Long and Short).
    """
    __tablename__ = "positions"

    symbol: Mapped[str] = mapped_column(String(16), primary_key=True, index=True)
    position_type: Mapped[str] = mapped_column(String(16), nullable=False)  # LONG, SHORT
    volume: Mapped[int] = mapped_column(Integer, nullable=False)
    avg_cost: Mapped[float] = mapped_column(Float, nullable=False)
    current_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    prior_close_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    unrealized_pnl: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    take_profit_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    stop_loss_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    is_sbl_pending_return: Mapped[bool] = mapped_column(Boolean, default=False)
    associated_sbl_lot_id: Mapped[Optional[str]] = mapped_column(String(64), ForeignKey("sbl_borrow_lots.lot_id"), nullable=True)
    opened_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)

    sbl_lot: Mapped[Optional["SBLBorrowLot"]] = relationship("SBLBorrowLot", back_populates="positions")


class SessionLog(Base):
    """
    Table tracking operational events, heartbeats, webhooks, and security alarms.
    """
    __tablename__ = "session_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)  # LOGIN_SUCCESS, HEARTBEAT_OK, RECONNECT, LOGOUT, WEBHOOK_RECEIVED, VALIDATION_ERROR, SECURITY_ALERT
    details: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)


class WatchlistTrigger(Base):
    """
    Table tracking conditional monitoring triggers (e.g. Stop Loss triggers, Trailing stops).
    """
    __tablename__ = "watchlist_triggers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(16), nullable=False)  # SELL, COVER, BUY
    volume: Mapped[int] = mapped_column(Integer, nullable=False)
    condition_type: Mapped[str] = mapped_column(String(32), nullable=False)  # PRICE_BELOW, PRICE_ABOVE, TIME_EXIT
    trigger_price: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="ACTIVE", index=True)  # ACTIVE, TRIGGERED, CANCELLED
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)


class MarketSnapshot(Base):
    """
    Table tracking market index snapshots (%Change, Current Index, High, Low, Volume, Value).
    Scraped during market monitoring periods (10:00-10:30, 12:00-12:30, 14:00-14:30, 16:00-16:30).
    """
    __tablename__ = "market_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    index_name: Mapped[str] = mapped_column(String(16), default="SET", index=True)
    current_index: Mapped[float] = mapped_column(Float, nullable=False)
    change_value: Mapped[float] = mapped_column(Float, default=0.0)
    pct_change: Mapped[float] = mapped_column(Float, nullable=False)
    high: Mapped[float] = mapped_column(Float, nullable=False)
    low: Mapped[float] = mapped_column(Float, nullable=False)
    volume_k: Mapped[float] = mapped_column(Float, default=0.0)
    value_mb: Mapped[float] = mapped_column(Float, default=0.0)
    period_name: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)


class WorkflowAnomaly(Base):
    """
    Table tracking execution anomalies detected during autonomous workflow runs.
    Flags workflows that need interactive re-learning in the IDE.
    """
    __tablename__ = "workflow_anomalies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workflow_name: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    failed_step: Mapped[str] = mapped_column(String(128), nullable=False)
    error_message: Mapped[str] = mapped_column(Text, nullable=False)
    snapshot_path: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="NEEDS_RELEARN", index=True)  # NEEDS_RELEARN, RESOLVED
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class AgentDecisionLog(Base):
    """
    Table storing structured agent reasoning, decisions, tool calls, and reflection outcomes
    as part of the PT-MRO memory architecture.
    """
    __tablename__ = "agent_decision_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    agent_name: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    action_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)  # PLAN, TOOL_CALL, REFLECTION, ANNEAL, KILL_SWITCH
    regime: Mapped[Optional[str]] = mapped_column(String(32), nullable=True, index=True)
    thought: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    input_context: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    output_result: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_success: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)
