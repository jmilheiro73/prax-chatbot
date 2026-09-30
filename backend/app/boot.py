"""Boot chain (padrão da Live 04): recursos compartilhados sobem em ordem e descem ao contrário.

    settings -> SummaryStore (SQLite) -> AsyncRedisSaver (TTL) -> LLM -> tools -> AgentRunner

Tudo entra num `AsyncExitStack`; o `lifespan` do FastAPI é só `async with boot(app)`.
"""

from __future__ import annotations

from contextlib import AsyncExitStack, asynccontextmanager
from dataclasses import dataclass
from typing import AsyncIterator

from fastapi import FastAPI
from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.redis.aio import AsyncRedisSaver

from app.agent.graph import CompactionPolicy
from app.agent.runner import AgentRunner
from app.agent.tools import load_tools
from app.memory.summary_store import SummaryStore
from app.settings import Settings, load_settings


@dataclass
class Resources:
    settings: Settings
    runner: AgentRunner


@asynccontextmanager
async def boot(settings: Settings | None = None, llm: BaseChatModel | None = None) -> AsyncIterator[Resources]:
    """`llm` é injetável para testes end-to-end sem OpenAI (ver tests/e2e_app.py)."""
    settings = settings or load_settings()
    async with AsyncExitStack() as stack:
        # 1. Longo prazo: onde o summary vive.
        summary_store = await SummaryStore(settings.summary_db_path).open()
        stack.push_async_callback(summary_store.close)

        # 2. Curto prazo: checkpointer no Redis com TTL (D3 · AC-02).
        #    `refresh_on_read=True`: cada mensagem renova o TTL — "parou de usar, expira".
        checkpointer = await stack.enter_async_context(
            AsyncRedisSaver.from_conn_string(
                settings.redis_url,
                ttl={"default_ttl": settings.checkpoint_ttl_minutes, "refresh_on_read": True},
            )
        )
        await checkpointer.asetup()

        # 3. Modelo + tools + runner.
        llm = llm or ChatOpenAI(model=settings.openai_model, api_key=settings.openai_api_key, streaming=True)
        policy = CompactionPolicy(settings.summary_token_limit, settings.summary_keep_last)
        runner = AgentRunner(llm, load_tools(), summary_store, policy, checkpointer)

        yield Resources(settings=settings, runner=runner)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    async with boot() as resources:
        app.state.resources = resources
        yield
