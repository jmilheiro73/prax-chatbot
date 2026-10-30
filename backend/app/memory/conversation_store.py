"""Transcript durável (Aula 11): `conversation`, `interaction` e o gasto por chamada.

O checkpoint no Redis retoma a execução e expira. Esta tabela é o que reconstrói a tela e sobrevive ao TTL.
- Grava o evento terminal (`on_chat_model_end`, `on_tool_end`), nunca delta.
- `message` guarda o JSON da mensagem como o framework entrega.
- `sequence` ordena dentro da conversa e `deleted_at` é o tombstone: apagar esconde, não destrói.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import aiosqlite

_SCHEMA = """
CREATE TABLE IF NOT EXISTS conversation (
    thread_id     TEXT PRIMARY KEY,
    user_id       TEXT NOT NULL,
    title         TEXT NOT NULL,
    title_source  TEXT NOT NULL DEFAULT 'first_message',
    created_at    TEXT NOT NULL,
    last_used_at  TEXT NOT NULL,
    deleted_at    TEXT
);
CREATE INDEX IF NOT EXISTS conversation_recent ON conversation (user_id, last_used_at);

CREATE TABLE IF NOT EXISTS interaction (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    thread_id   TEXT NOT NULL REFERENCES conversation (thread_id),
    sequence    INTEGER NOT NULL,
    role        TEXT NOT NULL CHECK (role IN ('human', 'ai', 'tool')),
    run_id      TEXT,
    message     TEXT NOT NULL,
    feedback    TEXT CHECK (feedback IN ('up', 'down')),
    created_at  TEXT NOT NULL,
    UNIQUE (thread_id, sequence)
);
CREATE INDEX IF NOT EXISTS interaction_run ON interaction (thread_id, run_id);

CREATE TABLE IF NOT EXISTS llm_usage (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    thread_id      TEXT,
    purpose        TEXT NOT NULL,
    input_tokens   INTEGER NOT NULL,
    output_tokens  INTEGER NOT NULL,
    created_at     TEXT NOT NULL
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class Conversation:
    thread_id: str
    title: str
    title_source: str
    last_used_at: str


class ConversationStore:
    def __init__(self, db: aiosqlite.Connection, user_id: str):
        self._db = db
        self._user_id = user_id

    async def setup(self) -> None:
        await self._db.executescript(_SCHEMA)
        await self._db.commit()

    async def start_turn(self, thread_id: str, message: str) -> None:
        """A conversa nasce na primeira mensagem, não ao abrir o chat vazio (Aula 11)."""
        now = _now()
        await self._db.execute(
            """
            INSERT INTO conversation (thread_id, user_id, title, created_at, last_used_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT (thread_id) DO UPDATE SET last_used_at = excluded.last_used_at, deleted_at = NULL
            """,
            (thread_id, self._user_id, message.split("\n")[0][:80], now, now),
        )
        await self.append(thread_id, "human", {"type": "human", "content": message})

    async def append(self, thread_id: str, role: str, message: dict[str, Any], run_id: str | None = None) -> None:
        await self._db.execute(
            """
            INSERT INTO interaction (thread_id, sequence, role, run_id, message, created_at)
            VALUES (?, (SELECT COALESCE(MAX(sequence), 0) + 1 FROM interaction WHERE thread_id = ?), ?, ?, ?, ?)
            """,
            (thread_id, thread_id, role, run_id, json.dumps(message, ensure_ascii=False, default=str), _now()),
        )
        await self._db.commit()

    async def transcript(self, thread_id: str) -> list[dict[str, Any]]:
        """As mensagens no formato do snapshot, com `run_id` e `feedback` para o front."""
        async with self._db.execute(
            "SELECT run_id, message, feedback FROM interaction WHERE thread_id = ? ORDER BY sequence", (thread_id,)
        ) as cur:
            rows = await cur.fetchall()
        return [{**json.loads(r["message"]), "run_id": r["run_id"], "feedback": r["feedback"]} for r in rows]

    async def get(self, thread_id: str) -> Conversation | None:
        async with self._db.execute(
            "SELECT thread_id, title, title_source, last_used_at FROM conversation WHERE thread_id = ?", (thread_id,)
        ) as cur:
            row = await cur.fetchone()
        return Conversation(*row) if row else None

    async def list_recent(self, limit: int = 100) -> list[Conversation]:
        async with self._db.execute(
            """
            SELECT thread_id, title, title_source, last_used_at FROM conversation
            WHERE user_id = ? AND deleted_at IS NULL ORDER BY last_used_at DESC LIMIT ?
            """,
            (self._user_id, limit),
        ) as cur:
            return [Conversation(*r) for r in await cur.fetchall()]

    async def set_title(self, thread_id: str, title: str) -> None:
        await self._db.execute(
            "UPDATE conversation SET title = ?, title_source = 'llm' WHERE thread_id = ?", (title, thread_id)
        )
        await self._db.commit()

    async def soft_delete(self, thread_id: str) -> bool:
        cur = await self._db.execute(
            "UPDATE conversation SET deleted_at = ? WHERE thread_id = ? AND deleted_at IS NULL", (_now(), thread_id)
        )
        await self._db.commit()
        return cur.rowcount > 0

    async def set_feedback(self, thread_id: str, run_id: str, value: str | None) -> bool:
        cur = await self._db.execute(
            "UPDATE interaction SET feedback = ? WHERE thread_id = ? AND run_id = ? AND role = 'ai'",
            (value, thread_id, run_id),
        )
        await self._db.commit()
        return cur.rowcount > 0

    async def record_usage(self, thread_id: str | None, purpose: str, usage: dict[str, Any] | None) -> None:
        """O número que vale é o `usage` da resposta (Aula 02), não o tiktoken. Sem `usage`, não há o que gravar."""
        if not usage:
            return
        await self._db.execute(
            "INSERT INTO llm_usage (thread_id, purpose, input_tokens, output_tokens, created_at) VALUES (?, ?, ?, ?, ?)",
            (thread_id, purpose, usage.get("input_tokens", 0), usage.get("output_tokens", 0), _now()),
        )
        await self._db.commit()

    async def rated_down(self) -> list[dict[str, Any]]:
        """Respostas com 👎 e a pergunta que as gerou: a fila de anotação da Live 08."""
        async with self._db.execute(
            """
            SELECT a.thread_id, a.message AS answer,
                   (SELECT h.message FROM interaction h
                    WHERE h.thread_id = a.thread_id AND h.role = 'human' AND h.sequence < a.sequence
                    ORDER BY h.sequence DESC LIMIT 1) AS question
            FROM interaction a WHERE a.feedback = 'down' ORDER BY a.id
            """
        ) as cur:
            rows = await cur.fetchall()
        return [
            {
                "thread_id": r["thread_id"],
                "question": json.loads(r["question"])["content"] if r["question"] else "",
                "answer": json.loads(r["answer"])["content"],
            }
            for r in rows
        ]

    async def metrics(self) -> dict[str, Any]:
        """Eval online no mínimo (Live 08): sinais de runs reais, sem dashboard."""
        async def scalar(sql: str) -> int:
            async with self._db.execute(sql) as cur:
                row = await cur.fetchone()
            return int(row[0] or 0)

        async with self._db.execute(
            "SELECT purpose, SUM(input_tokens), SUM(output_tokens), COUNT(*) FROM llm_usage GROUP BY purpose"
        ) as cur:
            usage = {r[0]: {"input_tokens": r[1], "output_tokens": r[2], "calls": r[3]} for r in await cur.fetchall()}
        return {
            "conversations": await scalar("SELECT COUNT(*) FROM conversation WHERE deleted_at IS NULL"),
            "answers": await scalar("SELECT COUNT(*) FROM interaction WHERE role = 'ai'"),
            "tool_results": await scalar("SELECT COUNT(*) FROM interaction WHERE role = 'tool'"),
            "tool_errors": await scalar(
                "SELECT COUNT(*) FROM interaction WHERE role = 'tool' AND json_extract(message, '$.status') = 'error'"
            ),
            "feedback": {
                "up": await scalar("SELECT COUNT(*) FROM interaction WHERE feedback = 'up'"),
                "down": await scalar("SELECT COUNT(*) FROM interaction WHERE feedback = 'down'"),
            },
            "usage_by_purpose": usage,
        }
