"""Configuração da aplicação.

Tudo vem de variáveis de ambiente / `.env` na RAIZ do repo (AC-05 do D3, AC-09 do P1).
Nenhum módulo lê `os.environ` por conta própria: quem precisa de config recebe um `Settings`.
"""

from __future__ import annotations

import os
from pathlib import Path

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# <repo>/backend/app/settings.py -> <repo>/.env
ROOT_ENV = Path(__file__).resolve().parents[2] / ".env"


class McpServerSetting(BaseModel):
    name: str
    url: str
    token: str | None = None
    allow: list[str] = ["*"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT_ENV, env_file_encoding="utf-8", extra="ignore")

    # --- OpenAI (P1) ---
    openai_api_key: str = Field(alias="OPENAI_API_KEY")
    openai_model: str = Field(default="gpt-4o-mini", alias="OPENAI_MODEL")

    # --- Checkpoint de curto prazo: Redis com TTL (D3 · AC-02) ---
    redis_url: str = Field(default="redis://localhost:6379", alias="REDIS_URL")
    # Aula: 24h (86400). Teste local: 60 -> a chave some depois de 1 minuto.
    checkpoint_ttl_seconds: int = Field(default=86_400, alias="CHECKPOINT_TTL_SECONDS")

    # --- Sumarização: memória de longo prazo desta entrega (D3 · AC-03) ---
    # Quando o histórico (tudo menos a mensagem atual) passa disso, compacta.
    # Teste: 10 -> qualquer mensagem longa dispara.
    summary_token_limit: int = Field(default=4_000, alias="SUMMARY_TOKEN_LIMIT")
    # Quantas mensagens recentes sobrevivem à compactação (0 = só o summary).
    summary_keep_last: int = Field(default=2, alias="SUMMARY_KEEP_LAST")
    # Onde o summary vive. Sobrevive ao TTL do Redis — é isso que o torna "longo prazo".
    summary_db_path: str = Field(default="data/summaries.sqlite", alias="SUMMARY_DB_PATH")

    # --- Durável: conversas, memórias e documentos ---
    app_db_path: str = Field(default="data/prax.sqlite", alias="APP_DB_PATH")
    # Sem login por enquanto: um usuário só, com a chave pronta para quando houver auth.
    user_id: str = Field(default="local", alias="USER_ID")
    timezone: str = Field(default="America/Sao_Paulo", alias="APP_TIMEZONE")
    recursion_limit: int = Field(default=25, alias="RECURSION_LIMIT")

    # --- RAG (Aulas 14 a 16) ---
    embedding_model: str = Field(default="text-embedding-3-small", alias="EMBEDDING_MODEL")
    embedding_dims: int = Field(default=1536, alias="EMBEDDING_DIMS")
    rag_top_k: int = Field(default=5, alias="RAG_TOP_K")
    rag_chunk_tokens: int = Field(default=400, alias="RAG_CHUNK_TOKENS")
    # Custa uma chamada de LLM por chunk novo, por isso vem desligado.
    rag_enrich: bool = Field(default=False, alias="RAG_ENRICH")
    # Evals usam outro prefixo, para não encostar nos índices de quem está usando o app.
    index_prefix: str = Field(default="prax", alias="INDEX_PREFIX")
    hnsw_m: int = Field(default=16, alias="HNSW_M")
    hnsw_ef_construction: int = Field(default=64, alias="HNSW_EF_CONSTRUCTION")

    # --- Memória de longo prazo (Aulas 11 e 12) ---
    memory_enabled: bool = Field(default=True, alias="MEMORY_ENABLED")
    memory_min_similarity: float = Field(default=0.35, alias="MEMORY_MIN_SIMILARITY")

    # --- Subagente (Aula 19): vazio usa o mesmo modelo do orquestrador ---
    subagent_model: str = Field(default="", alias="SUBAGENT_MODEL")

    # --- MCP (Live 09) ---
    # Token de quem chama o nosso servidor; vazio deixa a rota /mcp desligada. Não é a chave da OpenAI.
    mcp_server_token: str = Field(default="", alias="MCP_SERVER_TOKEN")
    # Servidores externos, em JSON: [{"name": "x", "url": "...", "token": "...", "allow": ["list_*"]}]
    mcp_servers: list[McpServerSetting] = Field(default=[], alias="MCP_SERVERS")

    # --- Front ---
    cors_origins: list[str] = Field(default=["http://localhost:3000"], alias="CORS_ORIGINS")

    # --- LangSmith (D3 · AC-04) ---
    langsmith_tracing: str = Field(default="", alias="LANGSMITH_TRACING")
    langsmith_api_key: str = Field(default="", alias="LANGSMITH_API_KEY")
    langsmith_project: str = Field(default="", alias="LANGSMITH_PROJECT")

    def export_tracing_env(self) -> None:
        """O SDK do LangSmith só olha o `os.environ`, e o pydantic-settings lê o `.env` sem escrever lá."""
        for name, value in (
            ("LANGSMITH_TRACING", self.langsmith_tracing),
            ("LANGSMITH_API_KEY", self.langsmith_api_key),
            ("LANGSMITH_PROJECT", self.langsmith_project),
        ):
            if value:
                os.environ.setdefault(name, value)

    @property
    def checkpoint_ttl_minutes(self) -> float:
        """`langgraph-checkpoint-redis` mede TTL em minutos."""
        return self.checkpoint_ttl_seconds / 60


def load_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]  (campos vêm do ambiente)
