"""Fila de anotação (Live 08): resposta com 👎 vira item de dataset, para um humano revisar.

    uv run python -m evals.export_feedback

Grava em `evals/datasets/from_feedback.jsonl`, sem repetir pergunta. O `expect` sai vazio de propósito: quem revisa
escreve o que era esperado e move o item para o `chat.jsonl`.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from app.db import open_database
from app.memory.conversation_store import ConversationStore
from app.settings import load_settings

OUTPUT = Path(__file__).parent / "datasets" / "from_feedback.jsonl"


def merge_items(existing: list[dict], rated: list[dict]) -> list[dict]:
    seen = {item["input"] for item in existing}
    merged = list(existing)
    for row in rated:
        if row["question"] and row["question"] not in seen:
            seen.add(row["question"])
            merged.append(
                {
                    "id": f"feedback-{len(merged) + 1}",
                    "scenario": "feedback",
                    "input": row["question"],
                    "bad_answer": row["answer"],
                    "expect": {},
                }
            )
    return merged


async def main() -> None:
    settings = load_settings()
    db = await open_database(settings.app_db_path)
    try:
        conversations = ConversationStore(db, settings.user_id)
        await conversations.setup()
        rated = await conversations.rated_down()
    finally:
        await db.close()
    existing = [json.loads(line) for line in OUTPUT.read_text(encoding="utf-8").splitlines()] if OUTPUT.exists() else []
    merged = merge_items(existing, rated)
    OUTPUT.write_text("".join(json.dumps(i, ensure_ascii=False) + "\n" for i in merged), encoding="utf-8")
    print(f"{len(merged) - len(existing)} item(ns) novo(s) em {OUTPUT}")


if __name__ == "__main__":
    asyncio.run(main())
