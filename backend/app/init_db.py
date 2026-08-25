"""Database initialisation script — create tables and seed the default admin."""

import asyncio

from sqlalchemy import select

from app.core.deps import engine, async_session_factory
from app.core.security import get_password_hash
from app.models.base import Base
# Import all models so Base.metadata knows about them
import app.models  # noqa: F401
from app.models.user import User

DEFAULT_ADMIN_USERNAME = "admin"
DEFAULT_ADMIN_PASSWORD = "admin123"


async def init_db() -> None:
    """Create all tables and insert the default admin user if it does not exist."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with async_session_factory() as session:
        result = await session.execute(
            select(User).where(User.username == DEFAULT_ADMIN_USERNAME)
        )
        if result.scalar_one_or_none() is None:
            admin = User(
                username=DEFAULT_ADMIN_USERNAME,
                password_hash=get_password_hash(DEFAULT_ADMIN_PASSWORD),
                role="admin",
                status="active",
            )
            session.add(admin)
            await session.commit()
            print(f"[init_db] Default admin created: {DEFAULT_ADMIN_USERNAME}/{DEFAULT_ADMIN_PASSWORD}")
        else:
            print("[init_db] Default admin already exists, skipping.")


if __name__ == "__main__":
    asyncio.run(init_db())
