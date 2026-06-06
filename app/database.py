# app/database.py
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.sql import text
from app.config import settings

# Create the async engine
engine = create_async_engine(settings.DATABASE_URL, echo=True)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

# Helper to get the DB session
async def get_db():
    async with AsyncSessionLocal() as session:
        yield session

# --- ADD THESE TWO FUNCTIONS ---

async def create_all_tables():
    """Create all database tables."""
    from app.models import Base
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

async def check_db_connection():
    """Verify database connection."""
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
        return True