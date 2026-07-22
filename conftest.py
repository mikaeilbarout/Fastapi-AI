import os

# Tests stay on a throwaway SQLite file regardless of what database.py
# defaults to for dev/prod (currently Postgres) — faster, no external
# service required, and Base.metadata is portable across both dialects.
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./test.db")
os.environ.setdefault("REDIS_URL", "redis://localhost:16379/1")

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

import main
from database import Base, engine
from redis_client import redis_client


@pytest_asyncio.fixture
async def client():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    await redis_client.flushdb()

    # https (not http) so the Secure refresh_token cookie actually gets
    # attached to requests — ASGITransport never hits the network, so this
    # scheme is nominal only, no real TLS involved.
    transport = ASGITransport(app=main.app)
    async with AsyncClient(transport=transport, base_url="https://test") as ac:
        yield ac
