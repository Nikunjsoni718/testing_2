import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base

# Flaw 1: Hardcoded fallback database URL and echoing SQL in production
DB_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./inventory_dev.db")

engine = create_async_engine(
    DB_URL,
    echo=True, # Will leak sensitive queries into logs
    future=True
)

SessionLocal = async_sessionmaker(
    bind=engine, 
    class_=AsyncSession, 
    expire_on_commit=False
)

Base = declarative_base()

async def get_db():
    async with SessionLocal() as session:
        yield session
