from typing import AsyncGenerator, Optional
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from app.core.config import settings

# Primary Engine (Krungsri TradeMan - Real Money)
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    connect_args={"check_same_thread": False} if "sqlite" in settings.DATABASE_URL else {}
)

# Sandbox Engine (Settrade Click2Win - Virtual Simulation)
engine_click2win = create_async_engine(
    settings.CLICK2WIN_DATABASE_URL,
    echo=False,
    connect_args={"check_same_thread": False} if "sqlite" in settings.CLICK2WIN_DATABASE_URL else {}
)

# Session makers
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False
)

AsyncSessionClick2Win = async_sessionmaker(
    bind=engine_click2win,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False
)


def get_session_factory(platform: Optional[str] = None) -> async_sessionmaker[AsyncSession]:
    """Returns the appropriate sessionmaker based on target platform (CLICK2WIN vs TRADEMAN)."""
    plat = (platform or settings.TRADING_PLATFORM).upper()
    if plat == "CLICK2WIN":
        return AsyncSessionClick2Win
    return AsyncSessionLocal


async def get_db(platform: Optional[str] = None) -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency for yielding async database session dynamically based on platform."""
    factory = get_session_factory(platform)
    async with factory() as session:
        try:
            yield session
        finally:
            await session.close()
