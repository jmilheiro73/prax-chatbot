from __future__ import annotations

import os
import uuid

import pytest
import redis.asyncio as redis
from langgraph.checkpoint.memory import InMemorySaver

from app.agent.after_turn import AfterTurn
from app.agent.graph import CompactionPolicy
from app.agent.runner import AgentRunner
from app.agent.subagents import build_research_subagent, delegate_tool
from app.agent.tools import ToolContext, load_tools
from app.agent.tools.knowledge import specialist_tools
from app.background import BackgroundTasks
from app.db import open_database
from app.memory.conversation_store import ConversationStore
from app.memory.memory_store import MemoryStore
from app.memory.service import MemoryService
from app.memory.summary_store import SummaryStore
from app.rag.service import KnowledgeService
from app.rag.store import KnowledgeStore
from app.rag.vector_index import VectorIndex
from tests.fake_embeddings import FakeEmbeddings
from tests.fake_llm import FakeChatModel

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")


@pytest.fixture
async def summary_store(tmp_path):
    store = await SummaryStore(tmp_path / "summaries.sqlite").open()
    yield store
    await store.close()


@pytest.fixture
def fake_llm() -> FakeChatModel:
    return FakeChatModel()


def make_runner(llm, store, token_limit: int = 4000, keep_last: int = 2, checkpointer=None, **extra) -> AgentRunner:
    tools = extra.pop("tools", None)
    return AgentRunner(
        llm,
        tools if tools is not None else load_tools(),
        store,
        CompactionPolicy(token_limit=token_limit, keep_last=keep_last),
        checkpointer or InMemorySaver(),
        **extra,
    )


@pytest.fixture
def runner(fake_llm, summary_store) -> AgentRunner:
    return make_runner(fake_llm, summary_store)


@pytest.fixture
async def db(tmp_path):
    connection = await open_database(tmp_path / "prax.sqlite")
    yield connection
    await connection.close()


@pytest.fixture
async def conversations(db) -> ConversationStore:
    store = ConversationStore(db, "tester")
    await store.setup()
    return store


@pytest.fixture
def fake_embeddings() -> FakeEmbeddings:
    return FakeEmbeddings()


async def _open_index(name: str) -> VectorIndex:
    try:
        client = redis.from_url(REDIS_URL)
        await client.ping()
        await client.aclose()
    except Exception:
        pytest.skip("sem Redis em REDIS_URL")
    return await VectorIndex(f"prax-test:{name}:{uuid.uuid4().hex[:8]}", FakeEmbeddings.DIMS, REDIS_URL).open()


@pytest.fixture
async def chunk_index():
    index = await _open_index("chunks")
    yield index
    await index.drop()
    await index.close()


@pytest.fixture
async def knowledge(db, chunk_index, fake_embeddings):
    store = KnowledgeStore(db, "tester")
    await store.setup()
    service = KnowledgeService(store, chunk_index, fake_embeddings, "fake", top_k=3)
    await service.start()
    yield service
    await service.stop()


@pytest.fixture
async def memory_index():
    index = await _open_index("memories")
    yield index
    await index.drop()
    await index.close()


@pytest.fixture
async def memory(db, memory_index, fake_embeddings, fake_llm, conversations) -> MemoryService:
    store = MemoryStore(db, "tester")
    await store.setup()
    service = MemoryService(
        store, memory_index, fake_embeddings, "fake", "tester", fake_llm, conversations, min_similarity=0.15
    )
    await service.start()
    return service


@pytest.fixture
def full_runner(fake_llm, summary_store, conversations, knowledge, memory) -> AgentRunner:
    """O runner como o boot monta: transcript, memória, base de conhecimento e subagente."""
    subagent = build_research_subagent(fake_llm, specialist_tools(knowledge))
    tools = [*load_tools(ToolContext(knowledge=knowledge)), delegate_tool(subagent, conversations)]
    return make_runner(
        fake_llm, summary_store, tools=tools, conversations=conversations, memory=memory,
        after_turn=AfterTurn(fake_llm, conversations, memory), background=BackgroundTasks(),
    )
