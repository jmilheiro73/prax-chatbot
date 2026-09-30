"""Runner: a única fronteira entre o app e o LangGraph (P1 · AC-02).

Compila o grafo, chama `astream_events` e entrega `StreamEvent`s prontos.
A rota HTTP recebe este objeto por injeção de dependência e só faz o encode em SSE.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, AsyncIterator

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool
from langgraph.checkpoint.base import BaseCheckpointSaver

from app.agent.graph import GRAPH_NAME, SUMMARIZER_TAG, CompactionPolicy, build_graph
from app.memory.summary_store import SummaryStore


@dataclass(frozen=True)
class ThreadSnapshot:
    thread_id: str
    summary: str | None
    messages: list[dict[str, Any]]
    checkpoint_alive: bool


class AgentRunner:
    def __init__(
        self,
        llm: BaseChatModel,
        tools: list[BaseTool],
        summary_store: SummaryStore,
        policy: CompactionPolicy,
        checkpointer: BaseCheckpointSaver | None,
    ):
        self._summary_store = summary_store
        self._graph = build_graph(llm, tools, summary_store, policy, checkpointer)

    @staticmethod
    def _config(thread_id: str) -> RunnableConfig:
        return {"configurable": {"thread_id": thread_id}, "run_name": GRAPH_NAME}

    async def stream(self, message: str, thread_id: str) -> AsyncIterator[dict[str, Any]]:
        """P1 · AC-04: v2, só chat_model e tool. O front nunca recebe outro tipo."""
        async for event in self._graph.astream_events(
            {"messages": [HumanMessage(content=message)]},
            config=self._config(thread_id),
            version="v2",
            include_types=["chat_model", "tool"],
        ):
            # A LLM da sumarização também é `chat_model`; não é conversa, não vai para a tela.
            if SUMMARIZER_TAG in (event.get("tags") or []):
                continue
            yield event

    async def snapshot(self, thread_id: str) -> ThreadSnapshot:
        """Bônus (Live 04): o que o back sabe da thread — checkpoint quente + summary durável."""
        state = await self._graph.aget_state(self._config(thread_id))
        stored = await self._summary_store.get(thread_id)
        messages = state.values.get("messages", []) if state and state.values else []
        return ThreadSnapshot(
            thread_id=thread_id,
            summary=(stored.summary if stored else None),
            messages=[m.model_dump(include={"type", "content", "tool_calls", "name", "id"}) for m in messages],
            checkpoint_alive=bool(messages),
        )
