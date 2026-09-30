"""Configuração da aplicação.

Tudo vem de variáveis de ambiente / `.env` na RAIZ do repo (AC-05 do D3, AC-09 do P1).
Nenhum módulo lê `os.environ` por conta própria: quem precisa de config recebe um `Settings`.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# <repo>/backend/app/settings.py -> <repo>/.env
ROOT_ENV = Path(__file__).resolve().parents[2] / ".env"


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

    # --- Front ---
    cors_origins: list[str] = Field(default=["http://localhost:3000"], alias="CORS_ORIGINS")

    # LANGSMITH_TRACING / LANGSMITH_API_KEY / LANGSMITH_PROJECT (D3 · AC-04) são lidas
    # direto pelo SDK do LangSmith a partir do ambiente; não precisam passar por aqui.

    @property
    def checkpoint_ttl_minutes(self) -> float:
        """`langgraph-checkpoint-redis` mede TTL em minutos."""
        return self.checkpoint_ttl_seconds / 60


def load_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]  (campos vêm do ambiente)
