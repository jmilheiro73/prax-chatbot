"""Runner: a única fronteira entre o app e o LangGraph (P1 · AC-02).

Compila o grafo, chama `astream_events` e entrega `StreamEvent`s prontos.
A rota HTTP recebe este objeto por injeção de dependência e só faz o encode em SSE.
No caminho, grava o evento terminal no transcript durável e, no fim do turno, dispara o que não pode atrasar a resposta.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, AsyncIterator, Awaitable, Callable

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool
from langgraph.checkpoint.base import BaseCheckpointSaver

from app.agent.after_turn import AfterTurn
from app.agent.graph import GRAPH_NAME, SUMMARIZER_TAG, CompactionPolicy, build_graph
from app.agent.subagents import SUBAGENT_TAG
from app.agent.tokens import message_text
from app.background import BackgroundTasks
from app.memory.conversation_store import ConversationStore
from app.memory.service import MemoryService
from app.memory.summary_store import SummaryStore

logger = logging.getLogger(__name__)
# Tokens que não são conversa não vão para a tela (AC-04).
_HIDDEN_TAGS = {SUMMARIZER_TAG, SUBAGENT_TAG}


@dataclass(frozen=True)
class ThreadSnapshot:
    thread_id: str
    summary: str | None
    messages: list[dict[str, Any]]
    checkpoint_alive: bool
    transcript: list[dict[str, Any]]


class AgentRunner:
    def __init__(
        self,
        llm: BaseChatModel,
        tools: list[BaseTool],
        summary_store: SummaryStore,
        policy: CompactionPolicy,
        checkpointer: BaseCheckpointSaver | None,
        *,
        conversations: ConversationStore | None = None,
        memory: MemoryService | None = None,
        after_turn: AfterTurn | None = None,
        background: BackgroundTasks | None = None,
        runtime_context: Callable[[], Awaitable[dict[str, str]]] | None = None,
        recursion_limit: int = 25,
    ):
        self._summary_store = summary_store
        self._conversations = conversations
        self._after_turn = after_turn
        self._background = background or BackgroundTasks()
        self._recursion_limit = recursion_limit
        self._graph = build_graph(
            llm, tools, summary_store, policy, checkpointer,
            memory=memory, conversations=conversations, runtime_context=runtime_context,
        )

    def _config(self, thread_id: str) -> RunnableConfig:
        return {"configurable": {"thread_id": thread_id}, "run_name": GRAPH_NAME, "recursion_limit": self._recursion_limit}

    async def stream(self, message: str, thread_id: str) -> AsyncIterator[dict[str, Any]]:
        """P1 · AC-04: v2, só chat_model e tool. O front nunca recebe outro tipo."""
        if self._conversations:
            await self._conversations.start_turn(thread_id, message)
        answer = ""
        async for event in self._graph.astream_events(
            {"messages": [HumanMessage(content=message)]},
            config=self._config(thread_id),
            version="v2",
            include_types=["chat_model", "tool"],
        ):
            if _HIDDEN_TAGS.intersection(event.get("tags") or []):
                continue
            await self._persist(thread_id, event)
            if event["event"] == "on_chat_model_end":
                answer = message_text(event["data"]["output"]) or answer
            yield event
        # Só chega aqui quem terminou: um turno cancelado não vira título nem memória.
        if self._after_turn and answer:
            self._background.spawn(self._after_turn.run(thread_id, message, answer), f"after-turn-{thread_id}")

    async def _persist(self, thread_id: str, event: dict[str, Any]) -> None:
        """Evento terminal, nunca delta (Aula 11). Falha aqui vai para o log: não derruba a resposta."""
        if not self._conversations:
            return
        output = event["data"].get("output")
        try:
            if event["event"] == "on_chat_model_end" and isinstance(output, AIMessage):
                message = output.model_dump(include={"type", "content", "tool_calls", "id"})
                message["usage"] = output.usage_metadata
                await self._conversations.append(thread_id, "ai", message, run_id=event["run_id"])
                await self._conversations.record_usage(thread_id, "chat", output.usage_metadata)
            elif event["event"] == "on_tool_end" and isinstance(output, ToolMessage):
                message = output.model_dump(include={"type", "content", "name", "tool_call_id", "status"})
                await self._conversations.append(thread_id, "tool", message, run_id=event["run_id"])
        except Exception:
            logger.exception("falha ao gravar o transcript da thread %s", thread_id)

    async def snapshot(self, thread_id: str) -> ThreadSnapshot:
        """Bônus (Live 04): o que o back sabe da thread.

        `messages` é o checkpoint quente, que expira e sofre compactação. `transcript` é o durável, que hidrata a tela.
        """
        state = await self._graph.aget_state(self._config(thread_id))
        stored = await self._summary_store.get(thread_id)
        messages = state.values.get("messages", []) if state and state.values else []
        return ThreadSnapshot(
            thread_id=thread_id,
            summary=(stored.summary if stored else None),
            messages=[m.model_dump(include={"type", "content", "tool_calls", "name", "id"}) for m in messages],
            checkpoint_alive=bool(messages),
            transcript=(await self._conversations.transcript(thread_id)) if self._conversations else [],
        )
