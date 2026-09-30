"""Integração (D3 · AC-02): checkpoint no Redis com TTL some; o summary no SQLite fica.

Precisa de um Redis com RediSearch em REDIS_URL (default redis://localhost:6379). Se não houver, pula.
"""

from __future__ import annotations

import asyncio
import os
import uuid

import pytest
import redis.asyncio as redis
from langgraph.checkpoint.redis.aio import AsyncRedisSaver

from tests.conftest import make_runner

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")


async def _redis_available() -> bool:
    try:
        r = redis.from_url(REDIS_URL)
        await r.ping()
        mods = {m[b"name"] if isinstance(m, dict) else m for m in await r.execute_command("MODULE LIST")}
        await r.aclose()
        return True
    except Exception:
        return False


async def test_checkpoint_expires_but_summary_stays(fake_llm, summary_store):
    if not await _redis_available():
        pytest.skip("Redis não disponível")
    ttl_seconds = 3
    thread = f"ttl-{uuid.uuid4()}"
    async with AsyncRedisSaver.from_conn_string(
        REDIS_URL, ttl={"default_ttl": ttl_seconds / 60, "refresh_on_read": True}
    ) as saver:
        await saver.asetup()
        runner = make_runner(fake_llm, summary_store, token_limit=10, keep_last=0, checkpointer=saver)

        async for _ in runner.stream("Meu nome é Ana, moro em Curitiba e gosto de café coado.", thread):
            pass
        async for _ in runner.stream("ok", thread):  # dispara a compactação
            pass
        assert (await runner.snapshot(thread)).checkpoint_alive
        assert (await summary_store.get(thread)) is not None

        await asyncio.sleep(ttl_seconds + 2)  # "parou de usar por um minutinho"

        snap = await runner.snapshot(thread)
        assert not snap.checkpoint_alive, "checkpoint deveria ter expirado no Redis"
        assert snap.summary is not None, "summary é longo prazo: sobrevive ao TTL"
