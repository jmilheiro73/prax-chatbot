from __future__ import annotations

import pytest
from langgraph.checkpoint.memory import InMemorySaver

from app.agent.graph import CompactionPolicy
from app.agent.runner import AgentRunner
from app.agent.tools import load_tools
from app.memory.summary_store import SummaryStore
from tests.fake_llm import FakeChatModel


@pytest.fixture
async def summary_store(tmp_path):
    store = await SummaryStore(tmp_path / "summaries.sqlite").open()
    yield store
    await store.close()


@pytest.fixture
def fake_llm() -> FakeChatModel:
    return FakeChatModel()


def make_runner(llm, store, token_limit: int = 4000, keep_last: int = 2, checkpointer=None) -> AgentRunner:
    return AgentRunner(
        llm,
        load_tools(),
        store,
        CompactionPolicy(token_limit=token_limit, keep_last=keep_last),
        checkpointer or InMemorySaver(),
    )


@pytest.fixture
def runner(fake_llm, summary_store) -> AgentRunner:
    return make_runner(fake_llm, summary_store)
