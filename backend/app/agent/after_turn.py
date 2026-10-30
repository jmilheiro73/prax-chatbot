"""O que acontece depois da resposta, fora do caminho crítico (Aula 11): título e extração de memória."""

from __future__ import annotations

from langchain_core.language_models import BaseChatModel

from app.agent.prompts import TITLE_PROMPT
from app.agent.schemas import ConversationTitle
from app.memory.conversation_store import ConversationStore
from app.memory.service import MemoryService


class AfterTurn:
    def __init__(self, llm: BaseChatModel, conversations: ConversationStore, memory: MemoryService | None):
        self._titler = llm.with_structured_output(ConversationTitle, include_raw=True)
        self._conversations = conversations
        self._memory = memory

    async def run(self, thread_id: str, user_message: str, assistant_message: str) -> None:
        await self._title_if_new(thread_id, user_message, assistant_message)
        if self._memory:
            await self._memory.extract(thread_id, user_message, assistant_message)

    async def _title_if_new(self, thread_id: str, user_message: str, assistant_message: str) -> None:
        conversation = await self._conversations.get(thread_id)
        if conversation is None or conversation.title_source == "llm":
            return
        result = await self._titler.ainvoke(
            TITLE_PROMPT.format(user_message=user_message, assistant_message=assistant_message)
        )
        await self._conversations.record_usage(thread_id, "title", getattr(result["raw"], "usage_metadata", None))
        if result["parsed"] is not None:
            await self._conversations.set_title(thread_id, result["parsed"].title.strip()[:80])
