"""Conexão SQLite do que é durável: conversas, memórias e documentos.

"O melhor sistema é o que vai para prod" (Live 06): SQLite basta para um usuário em localhost.
Cada store fala SQL só com esta conexão, então trocar por Postgres é trocar os stores.
"""

from __future__ import annotations

from pathlib import Path

import aiosqlite


async def open_database(path: str | Path) -> aiosqlite.Connection:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    db = await aiosqlite.connect(path)
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA journal_mode=WAL")
    await db.execute("PRAGMA foreign_keys=ON")
    return db
