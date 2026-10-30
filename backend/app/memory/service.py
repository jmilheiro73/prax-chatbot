"""Memória de longo prazo (Aulas 11 e 12): extrair fora do caminho crítico, recuperar por relevância.

Teste de aceite da aula: a conversa A cria o fato, a conversa B (sem checkpoint) usa, e a conversa C, sem relação,
não recebe nada.

- `profile` entra sempre; `fact` só com similaridade acima do threshold. Sem nada relevante, não injeta.
- Antes de gastar LLM, um filtro determinístico (Live 03) descarta o que não fala do usuário.
- Memória é vetor de ataque (Live 05): além do prompt de defesa, um filtro barra instrução e dado sensível.
"""

from __future__ import annotations

import logging
import re

from langchain_core.embeddings import Embeddings
from langchain_core.language_models import BaseChatModel

from app.agent.prompts import EXTRACT_MEMORY_PROMPT
from app.agent.schemas import MemoryExtraction
from app.memory.conversation_store import ConversationStore
from app.memory.memory_store import Memory, MemoryStore
from app.rag.vector_index import VectorIndex, VectorItem, to_bytes

logger = logging.getLogger(__name__)

_ABOUT_THE_USER = re.compile(
    r"\b(eu|meu|minha|meus|minhas|me chamo|sou|moro|trabalho|prefiro|gosto|odeio|quero que|sempre|nunca)\b", re.I
)
_UNSAFE = re.compile(
    r"ignor\w*\s.*instru|system prompt|prompt do sistema|sk-[A-Za-z0-9_-]{8,}|senha|password|api[ _-]?key"
    r"|\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b|\b(?:\d[ -]?){13,16}\b",
    re.I,
)
# Acima disto, o fato novo é o mesmo que já existe.
_DUPLICATE_SIMILARITY = 0.92


def worth_extracting(message: str) -> bool:
    return len(message) >= 10 and _ABOUT_THE_USER.search(message) is not None


def is_safe_memory(content: str) -> bool:
    return _UNSAFE.search(content) is None


class MemoryService:
    def __init__(
        self,
        store: MemoryStore,
        index: VectorIndex,
        embeddings: Embeddings,
        embedding_model: str,
        user_id: str,
        llm: BaseChatModel,
        conversations: ConversationStore | None = None,
        min_similarity: float = 0.35,
        top_k: int = 5,
    ):
        self._store = store
        self._index = index
        self._embeddings = embeddings
        self._embedding_model = embedding_model
        self._user_id = user_id
        self._conversations = conversations
        self._min_similarity = min_similarity
        self._top_k = top_k
        self._extractor = llm.with_structured_output(MemoryExtraction, include_raw=True)

    async def start(self) -> None:
        rows = [m for m in await self._store.list_all() if m.embedding_model == self._embedding_model]
        if await self._index.count() != len(rows):
            await self._index.upsert([VectorItem(m.id, self._user_id, m.embedding) for m in rows], wait=False)

    async def recall(self, query: str) -> list[str]:
        """O recorte para este turno. Se a busca falhar, a conversa segue sem memória."""
        profile = await self._store.list_all("profile")
        try:
            vector = await self._embeddings.aembed_query(query)
            hits = await self._index.search(vector, self._top_k + len(profile), scope=self._user_id)
        except Exception:
            logger.exception("falha ao buscar memórias")
            return [m.content for m in profile]
        relevant = [h.id for h in hits if h.similarity >= self._min_similarity]
        facts = [m for m in await self._store.by_ids(relevant) if m.type == "fact"][: self._top_k]
        return [m.content for m in (*profile, *facts)]

    async def extract(self, thread_id: str, user_message: str, assistant_message: str) -> list[Memory]:
        if not worth_extracting(user_message):
            return []
        prompt = EXTRACT_MEMORY_PROMPT.format(user_message=user_message, assistant_message=assistant_message)
        result = await self._extractor.ainvoke(prompt)
        if self._conversations:
            await self._conversations.record_usage(thread_id, "memory", getattr(result["raw"], "usage_metadata", None))
        parsed: MemoryExtraction | None = result["parsed"]
        if parsed is None:
            return []
        saved = []
        for item in parsed.memories:
            content = item.content.strip()
            if not content or not is_safe_memory(content):
                logger.warning("memória descartada pelo filtro de segurança")
                continue
            memory = await self._add_if_new(item.type, content, thread_id)
            if memory:
                saved.append(memory)
        return saved

    async def _add_if_new(self, type: str, content: str, thread_id: str | None) -> Memory | None:
        vector = await self._embeddings.aembed_query(content)
        hits = await self._index.search(vector, 1, scope=self._user_id)
        if hits and hits[0].similarity >= _DUPLICATE_SIMILARITY:
            return None
        return await self._save(type, content, thread_id, vector)

    async def _save(self, type: str, content: str, thread_id: str | None, vector: list[float]) -> Memory:
        embedding = to_bytes(vector)
        memory = await self._store.add(type, content, thread_id, embedding, self._embedding_model)
        await self._index.upsert([VectorItem(memory.id, self._user_id, embedding)])
        return memory

    async def list_memories(self) -> list[Memory]:
        return await self._store.list_all()

    async def create(self, type: str, content: str) -> Memory:
        return await self._save(type, content, None, await self._embeddings.aembed_query(content))

    async def update(self, memory_id: str, content: str) -> Memory | None:
        if await self._store.get(memory_id) is None:
            return None
        embedding = to_bytes(await self._embeddings.aembed_query(content))
        memory = await self._store.update(memory_id, content, embedding, self._embedding_model)
        await self._index.upsert([VectorItem(memory_id, self._user_id, embedding)])
        return memory

    async def delete(self, memory_id: str) -> bool:
        deleted = await self._store.delete(memory_id)
        if deleted:
            await self._index.delete([memory_id])
        return deleted
