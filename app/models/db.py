from datetime import datetime, timezone
from sqlalchemy import Column, String, Integer, DateTime
from sqlalchemy.orm import declarative_base
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from app.core.config import get_settings

Base = declarative_base()

class Project(Base):
    __tablename__ = 'projects'

    name = Column(String(100), primary_key=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    size_bytes = Column(Integer, default=0)
    uploads_count = Column(Integer, default=1)
    results_count = Column(Integer, default=0)

settings = get_settings()
engine = create_async_engine(f"sqlite+aiosqlite:///{settings.data_path}/reports.db", echo=False)
AsyncSessionLocal = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
