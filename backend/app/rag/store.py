"""Repository dos documentos e chunks: contrato do chunk da Aula 14.

Linhagem no próprio chunk (`doc_version`, `chunker_version`, `embedding_model`), para saber o que reprocessar
quando algo mudar. `context` fica separado de `content`: o enriquecimento entra no embedding, não na citação.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

import aiosqlite

_SCHEMA = """
CREATE TABLE IF NOT EXISTS document (
    id             TEXT PRIMARY KEY,
    user_id        TEXT NOT NULL,
    name           TEXT NOT NULL,
    version        INTEGER NOT NULL,
    content        TEXT NOT NULL,
    content_hash   TEXT NOT NULL,
    status         TEXT NOT NULL CHECK (status IN ('queued', 'chunking', 'embedding', 'ready', 'error')),
    error          TEXT,
    chunk_count    INTEGER NOT NULL DEFAULT 0,
    reused_chunks  INTEGER NOT NULL DEFAULT 0,
    created_at     TEXT NOT NULL,
    updated_at     TEXT NOT NULL,
    UNIQUE (user_id, name)
);
CREATE TABLE IF NOT EXISTS chunk (
    id               TEXT PRIMARY KEY,
    doc_id           TEXT NOT NULL REFERENCES document (id) ON DELETE CASCADE,
    doc_order        INTEGER NOT NULL,
    section          TEXT NOT NULL,
    content          TEXT NOT NULL,
    context          TEXT NOT NULL DEFAULT '',
    hash             TEXT NOT NULL,
    embedding        BLOB NOT NULL,
    embedding_model  TEXT NOT NULL,
    doc_version      INTEGER NOT NULL,
    chunker_version  TEXT NOT NULL,
    created_at       TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS chunk_order ON chunk (doc_id, doc_order);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class Document:
    id: str
    name: str
    version: int
    content_hash: str
    status: str
    error: str | None
    chunk_count: int
    reused_chunks: int
    updated_at: str


@dataclass(frozen=True)
class ChunkRow:
    id: str
    doc_id: str
    doc_name: str
    doc_order: int
    section: str
    content: str
    context: str
    hash: str
    embedding: bytes
    embedding_model: str


_DOC_COLUMNS = "id, name, version, content_hash, status, error, chunk_count, reused_chunks, updated_at"
_CHUNK_COLUMNS = """c.id, c.doc_id, d.name, c.doc_order, c.section, c.content, c.context, c.hash,
                    c.embedding, c.embedding_model"""


class KnowledgeStore:
    def __init__(self, db: aiosqlite.Connection, user_id: str):
        self._db = db
        self._user_id = user_id

    async def setup(self) -> None:
        await self._db.executescript(_SCHEMA)
        await self._db.commit()

    async def by_name(self, name: str) -> Document | None:
        async with self._db.execute(
            f"SELECT {_DOC_COLUMNS} FROM document WHERE user_id = ? AND name = ?", (self._user_id, name)
        ) as cur:
            row = await cur.fetchone()
        return Document(*row) if row else None

    async def get(self, doc_id: str) -> Document | None:
        async with self._db.execute(
            f"SELECT {_DOC_COLUMNS} FROM document WHERE user_id = ? AND id = ?", (self._user_id, doc_id)
        ) as cur:
            row = await cur.fetchone()
        return Document(*row) if row else None

    async def list_documents(self) -> list[Document]:
        async with self._db.execute(
            f"SELECT {_DOC_COLUMNS} FROM document WHERE user_id = ? ORDER BY name", (self._user_id,)
        ) as cur:
            return [Document(*r) for r in await cur.fetchall()]

    async def save_new_version(self, name: str, content: str, content_hash: str) -> Document:
        """Cria o documento, ou abre a próxima versão de um que já existe. Sempre volta para a fila."""
        now = _now()
        await self._db.execute(
            """
            INSERT INTO document (id, user_id, name, version, content, content_hash, status, created_at, updated_at)
            VALUES (?, ?, ?, 1, ?, ?, 'queued', ?, ?)
            ON CONFLICT (user_id, name) DO UPDATE SET
                version = document.version + 1, content = excluded.content, content_hash = excluded.content_hash,
                status = 'queued', error = NULL, updated_at = excluded.updated_at
            """,
            (uuid.uuid4().hex, self._user_id, name, content, content_hash, now, now),
        )
        await self._db.commit()
        saved = await self.by_name(name)
        assert saved is not None
        return saved

    async def pending_ids(self) -> list[str]:
        """Documentos que um boot anterior deixou pela metade voltam para a fila."""
        async with self._db.execute(
            "SELECT id FROM document WHERE user_id = ? AND status NOT IN ('ready', 'error')", (self._user_id,)
        ) as cur:
            return [r[0] for r in await cur.fetchall()]

    async def content_of(self, doc_id: str) -> str:
        async with self._db.execute("SELECT content FROM document WHERE id = ?", (doc_id,)) as cur:
            row = await cur.fetchone()
        return row[0] if row else ""

    async def set_status(self, doc_id: str, status: str, error: str | None = None) -> None:
        await self._db.execute(
            "UPDATE document SET status = ?, error = ?, updated_at = ? WHERE id = ?", (status, error, _now(), doc_id)
        )
        await self._db.commit()

    async def replace_chunks(self, doc: Document, rows: list[ChunkRow], chunker_version: str, reused: int) -> None:
        """Troca os chunks numa transação só: quem busca nunca vê o documento pela metade."""
        now = _now()
        await self._db.execute("DELETE FROM chunk WHERE doc_id = ?", (doc.id,))
        await self._db.executemany(
            """
            INSERT INTO chunk (id, doc_id, doc_order, section, content, context, hash, embedding, embedding_model,
                               doc_version, chunker_version, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (r.id, doc.id, r.doc_order, r.section, r.content, r.context, r.hash, r.embedding, r.embedding_model,
                 doc.version, chunker_version, now)
                for r in rows
            ],
        )
        await self._db.execute(
            "UPDATE document SET chunk_count = ?, reused_chunks = ?, updated_at = ? WHERE id = ?",
            (len(rows), reused, now, doc.id),
        )
        await self._db.commit()

    async def chunks_of(self, doc_id: str) -> list[ChunkRow]:
        async with self._db.execute(
            f"SELECT {_CHUNK_COLUMNS} FROM chunk c JOIN document d ON d.id = c.doc_id "
            "WHERE c.doc_id = ? ORDER BY c.doc_order",
            (doc_id,),
        ) as cur:
            return [ChunkRow(*r) for r in await cur.fetchall()]

    async def chunks_by_ids(self, ids: list[str]) -> list[ChunkRow]:
        if not ids:
            return []
        marks = ",".join("?" * len(ids))
        async with self._db.execute(
            f"SELECT {_CHUNK_COLUMNS} FROM chunk c JOIN document d ON d.id = c.doc_id WHERE c.id IN ({marks})", ids
        ) as cur:
            found = {r[0]: ChunkRow(*r) for r in await cur.fetchall()}
        return [found[i] for i in ids if i in found]

    async def neighbors(self, doc_id: str, order: int, radius: int) -> list[ChunkRow]:
        async with self._db.execute(
            f"SELECT {_CHUNK_COLUMNS} FROM chunk c JOIN document d ON d.id = c.doc_id "
            "WHERE c.doc_id = ? AND c.doc_order BETWEEN ? AND ? ORDER BY c.doc_order",
            (doc_id, order - radius, order + radius),
        ) as cur:
            return [ChunkRow(*r) for r in await cur.fetchall()]

    async def all_chunks(self) -> list[ChunkRow]:
        async with self._db.execute(
            f"SELECT {_CHUNK_COLUMNS} FROM chunk c JOIN document d ON d.id = c.doc_id WHERE d.user_id = ?",
            (self._user_id,),
        ) as cur:
            return [ChunkRow(*r) for r in await cur.fetchall()]

    async def delete(self, doc_id: str) -> None:
        await self._db.execute("DELETE FROM document WHERE user_id = ? AND id = ?", (self._user_id, doc_id))
        await self._db.commit()
