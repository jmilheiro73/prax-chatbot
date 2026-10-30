"""Tabela `memory` (Aula 11): `fact` e `profile`. O `summary` continua por thread, na `SummaryStore`.

"Memória é feature, merece tabela" (Live 05). A chave é o usuário, não a thread: é isso que deixa uma conversa nova
lembrar de outra. Toda linha é editável pelo usuário.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

import aiosqlite

_SCHEMA = """
CREATE TABLE IF NOT EXISTS memory (
    id                TEXT PRIMARY KEY,
    user_id           TEXT NOT NULL,
    type              TEXT NOT NULL CHECK (type IN ('fact', 'profile')),
    content           TEXT NOT NULL,
    source_thread_id  TEXT,
    embedding         BLOB NOT NULL,
    embedding_model   TEXT NOT NULL,
    created_at        TEXT NOT NULL,
    updated_at        TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS memory_user ON memory (user_id, type);
"""

_COLUMNS = "id, type, content, source_thread_id, embedding, embedding_model, updated_at"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class Memory:
    id: str
    type: str
    content: str
    source_thread_id: str | None
    embedding: bytes
    embedding_model: str
    updated_at: str


class MemoryStore:
    def __init__(self, db: aiosqlite.Connection, user_id: str):
        self._db = db
        self._user_id = user_id

    async def setup(self) -> None:
        await self._db.executescript(_SCHEMA)
        await self._db.commit()

    async def add(
        self, type: str, content: str, source_thread_id: str | None, embedding: bytes, embedding_model: str
    ) -> Memory:
        now = _now()
        memory_id = uuid.uuid4().hex
        await self._db.execute(
            """
            INSERT INTO memory (id, user_id, type, content, source_thread_id, embedding, embedding_model,
                                created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (memory_id, self._user_id, type, content, source_thread_id, embedding, embedding_model, now, now),
        )
        await self._db.commit()
        saved = await self.get(memory_id)
        assert saved is not None
        return saved

    async def get(self, memory_id: str) -> Memory | None:
        async with self._db.execute(
            f"SELECT {_COLUMNS} FROM memory WHERE user_id = ? AND id = ?", (self._user_id, memory_id)
        ) as cur:
            row = await cur.fetchone()
        return Memory(*row) if row else None

    async def by_ids(self, ids: list[str]) -> list[Memory]:
        if not ids:
            return []
        marks = ",".join("?" * len(ids))
        async with self._db.execute(
            f"SELECT {_COLUMNS} FROM memory WHERE user_id = ? AND id IN ({marks})", (self._user_id, *ids)
        ) as cur:
            found = {r[0]: Memory(*r) for r in await cur.fetchall()}
        return [found[i] for i in ids if i in found]

    async def list_all(self, type: str | None = None) -> list[Memory]:
        sql = f"SELECT {_COLUMNS} FROM memory WHERE user_id = ?"
        params: tuple = (self._user_id,)
        if type:
            sql += " AND type = ?"
            params += (type,)
        async with self._db.execute(f"{sql} ORDER BY updated_at DESC", params) as cur:
            return [Memory(*r) for r in await cur.fetchall()]

    async def update(self, memory_id: str, content: str, embedding: bytes, embedding_model: str) -> Memory | None:
        await self._db.execute(
            "UPDATE memory SET content = ?, embedding = ?, embedding_model = ?, updated_at = ? "
            "WHERE user_id = ? AND id = ?",
            (content, embedding, embedding_model, _now(), self._user_id, memory_id),
        )
        await self._db.commit()
        return await self.get(memory_id)

    async def delete(self, memory_id: str) -> bool:
        cur = await self._db.execute(
            "DELETE FROM memory WHERE user_id = ? AND id = ?", (self._user_id, memory_id)
        )
        await self._db.commit()
        return cur.rowcount > 0
