"""Boot chain (padrão da Live 04): recursos compartilhados sobem em ordem e descem ao contrário.

    settings -> HTTP client -> SummaryStore e banco -> AsyncRedisSaver (TTL) -> LLM e embeddings
             -> base de conhecimento -> memória -> tools e subagente -> AgentRunner

Tudo entra num `AsyncExitStack`; o `lifespan` do FastAPI é só `async with boot(app)`.
"""

from __future__ import annotations

import warnings
from contextlib import AsyncExitStack, asynccontextmanager
from dataclasses import dataclass
from datetime import datetime
from typing import AsyncIterator
from zoneinfo import ZoneInfo

import httpx
from fastapi import FastAPI
from langchain_core.embeddings import Embeddings
from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langgraph.checkpoint.redis.aio import AsyncRedisSaver

from app.agent.after_turn import AfterTurn
from app.agent.graph import CompactionPolicy
from app.agent.prompts import ENRICH_PROMPT
from app.agent.runner import AgentRunner
from app.agent.subagents import build_research_subagent, delegate_tool
from app.agent.tools import ToolContext, load_tools
from app.agent.tools.knowledge import specialist_tools
from app.agent.tools.mcp_client import McpServerConfig, load_mcp_tools
from app.background import BackgroundTasks
from app.db import open_database
from app.memory.conversation_store import ConversationStore
from app.memory.memory_store import MemoryStore
from app.memory.service import MemoryService
from app.memory.summary_store import SummaryStore
from app.rag.chunking import Chunk
from app.rag.service import Enricher, KnowledgeService
from app.rag.store import KnowledgeStore
from app.rag.vector_index import VectorIndex
from app.settings import Settings, load_settings

# O langchain-openai serializa a resposta com o `parsed` do output estruturado, e o pydantic reclama a cada chamada.
# O resultado sai certo; sem este filtro, o log só teria isso.
warnings.filterwarnings("ignore", message="Pydantic serializer warnings", category=UserWarning)


@dataclass
class Resources:
    settings: Settings
    runner: AgentRunner
    conversations: ConversationStore
    knowledge: KnowledgeService
    memory: MemoryService | None
    background: BackgroundTasks
    vector_indexes: list[VectorIndex]


def _chat_model(model: str, settings: Settings, http: httpx.AsyncClient) -> ChatOpenAI:
    # `stream_usage`: em streaming a OpenAI só manda o `usage` se pedirem (Aula 02: é esse o número que vale).
    return ChatOpenAI(
        model=model, api_key=settings.openai_api_key, streaming=True, stream_usage=True, http_async_client=http
    )


def _contextual_enricher(llm: BaseChatModel, conversations: ConversationStore) -> Enricher:
    async def enrich(document: str, chunk: Chunk) -> str:
        result = await llm.ainvoke(ENRICH_PROMPT.format(document=document[:12_000], chunk=chunk.content))
        await conversations.record_usage(None, "enrich", result.usage_metadata)
        return str(result.content).strip()

    return enrich


@asynccontextmanager
async def boot(
    settings: Settings | None = None,
    llm: BaseChatModel | None = None,
    embeddings: Embeddings | None = None,
) -> AsyncIterator[Resources]:
    """`llm` e `embeddings` são injetáveis para testes end-to-end sem OpenAI (ver tests/e2e_app.py)."""
    settings = settings or load_settings()
    async with AsyncExitStack() as stack:
        # 1. Um só pool de conexões para todos os clientes de modelo (Live 04): o gargalo de agente é conexão.
        http = httpx.AsyncClient(limits=httpx.Limits(max_connections=100, max_keepalive_connections=20))
        stack.push_async_callback(http.aclose)

        # 2. Longo prazo: summary, conversas, memórias e documentos.
        summary_store = await SummaryStore(settings.summary_db_path).open()
        stack.push_async_callback(summary_store.close)
        db = await open_database(settings.app_db_path)
        stack.push_async_callback(db.close)
        conversations = ConversationStore(db, settings.user_id)
        await conversations.setup()

        # 3. Curto prazo: checkpointer no Redis com TTL (D3 · AC-02).
        #    `refresh_on_read=True`: cada mensagem renova o TTL — "parou de usar, expira".
        checkpointer = await stack.enter_async_context(
            AsyncRedisSaver.from_conn_string(
                settings.redis_url,
                ttl={"default_ttl": settings.checkpoint_ttl_minutes, "refresh_on_read": True},
            )
        )
        await checkpointer.asetup()

        # 4. Modelos.
        specialist_llm = llm or _chat_model(settings.subagent_model or settings.openai_model, settings, http)
        llm = llm or _chat_model(settings.openai_model, settings, http)
        embeddings = embeddings or OpenAIEmbeddings(
            model=settings.embedding_model, api_key=settings.openai_api_key, http_async_client=http
        )

        # 5. Base de conhecimento: o worker sobe aqui e desce antes do banco.
        knowledge_store = KnowledgeStore(db, settings.user_id)
        await knowledge_store.setup()
        chunk_index = await VectorIndex(
            f"{settings.index_prefix}:chunks", settings.embedding_dims, settings.redis_url, settings.hnsw_m, settings.hnsw_ef_construction
        ).open()
        stack.push_async_callback(chunk_index.close)
        knowledge = KnowledgeService(
            knowledge_store,
            chunk_index,
            embeddings,
            settings.embedding_model,
            settings.rag_top_k,
            settings.rag_chunk_tokens,
            _contextual_enricher(llm, conversations) if settings.rag_enrich else None,
        )
        await knowledge.start()
        stack.push_async_callback(knowledge.stop)

        # 6. Memória de longo prazo.
        vector_indexes = [chunk_index]
        memory: MemoryService | None = None
        if settings.memory_enabled:
            memory_store = MemoryStore(db, settings.user_id)
            await memory_store.setup()
            memory_index = await VectorIndex(
                f"{settings.index_prefix}:memories", settings.embedding_dims, settings.redis_url,
                settings.hnsw_m, settings.hnsw_ef_construction,
            ).open()
            stack.push_async_callback(memory_index.close)
            vector_indexes.append(memory_index)
            memory = MemoryService(
                memory_store, memory_index, embeddings, settings.embedding_model, settings.user_id, llm,
                conversations, settings.memory_min_similarity,
            )
            await memory.start()

        # 7. Tools, subagente e runner.
        tools = load_tools(ToolContext(knowledge=knowledge))
        subagent = build_research_subagent(specialist_llm, specialist_tools(knowledge))
        tools.append(delegate_tool(subagent, conversations))
        tools.extend(await load_mcp_tools([McpServerConfig(**s.model_dump()) for s in settings.mcp_servers], http))

        async def runtime_context() -> dict[str, str]:
            now = datetime.now(ZoneInfo(settings.timezone))
            return {
                "agora": now.strftime("%Y-%m-%d %H:%M"),
                "fuso": settings.timezone,
                "documentos": await knowledge.status_line(),
            }

        background = BackgroundTasks()
        stack.push_async_callback(background.drain)
        policy = CompactionPolicy(settings.summary_token_limit, settings.summary_keep_last)
        runner = AgentRunner(
            llm, tools, summary_store, policy, checkpointer,
            conversations=conversations,
            memory=memory,
            after_turn=AfterTurn(llm, conversations, memory),
            background=background,
            runtime_context=runtime_context,
            recursion_limit=settings.recursion_limit,
        )

        yield Resources(
            settings=settings, runner=runner, conversations=conversations,
            knowledge=knowledge, memory=memory, background=background, vector_indexes=vector_indexes,
        )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = load_settings()
    settings.export_tracing_env()
    async with boot(settings) as resources:
        app.state.resources = resources
        yield
