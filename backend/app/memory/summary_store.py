"""Store do summary — a camada de LONGO prazo desta entrega (D3 · AC-03).

Decisão de produto (o PDF deixa livre): uma tabela `session(thread_id, summary, ...)` em SQLite.
Não é a tabela `memory_summaries` do case da Live 05 — é o mínimo que prova o conceito:
o summary sobrevive ao TTL do checkpoint no Redis, então quando o checkpoint expira a conversa
seguinte ainda "lembra" via system prompt.

Trocar por Postgres é trocar esta classe; o resto do app fala só com `SummaryStore`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import aiosqlite

_SCHEMA = """
CREATE TABLE IF NOT EXISTS session (
    thread_id    TEXT PRIMARY KEY,
    summary      TEXT NOT NULL,
    compactions  INTEGER NOT NULL DEFAULT 0,
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL
);
"""


@dataclass(frozen=True)
class SessionSummary:
    thread_id: str
    summary: str
    compactions: int
    updated_at: str


class SummaryStore:
    def __init__(self, db_path: str | Path):
        self._path = Path(db_path)
        self._db: aiosqlite.Connection | None = None

    async def open(self) -> "SummaryStore":
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(self._path)
        await self._db.executescript(_SCHEMA)
        await self._db.commit()
        return self

    async def close(self) -> None:
        if self._db is not None:
            await self._db.close()
            self._db = None

    @property
    def db(self) -> aiosqlite.Connection:
        if self._db is None:
            raise RuntimeError("SummaryStore não foi aberto (chame open() no boot chain)")
        return self._db

    async def get(self, thread_id: str) -> SessionSummary | None:
        async with self.db.execute(
            "SELECT thread_id, summary, compactions, updated_at FROM session WHERE thread_id = ?",
            (thread_id,),
        ) as cur:
            row = await cur.fetchone()
        return SessionSummary(*row) if row else None

    async def upsert(self, thread_id: str, summary: str) -> SessionSummary:
        now = datetime.now(timezone.utc).isoformat()
        await self.db.execute(
            """
            INSERT INTO session (thread_id, summary, compactions, created_at, updated_at)
            VALUES (?, ?, 1, ?, ?)
            ON CONFLICT(thread_id) DO UPDATE SET
                summary = excluded.summary,
                compactions = session.compactions + 1,
                updated_at = excluded.updated_at
            """,
            (thread_id, summary, now, now),
        )
        await self.db.commit()
        saved = await self.get(thread_id)
        assert saved is not None
        return saved
