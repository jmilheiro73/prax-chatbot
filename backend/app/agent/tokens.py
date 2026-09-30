"""Contagem de tokens para decidir quando compactar.

Usa o tokenizer da OpenAI (tiktoken) localmente — não é o `usage` real da API (Aula 02: nunca
confie no tiktoken para custo), mas para um LIMIAR de compactação serve, e não custa uma request.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Iterable

import tiktoken
from langchain_core.messages import BaseMessage


@lru_cache(maxsize=1)
def _encoding() -> tiktoken.Encoding:
    return tiktoken.get_encoding("o200k_base")


def message_text(msg: BaseMessage) -> str:
    """Texto "contável" de uma mensagem: conteúdo + tool calls, se houver."""
    content = msg.content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict):
                parts.append(str(block.get("text") or block.get("content") or ""))
            else:
                parts.append(str(block))
        content = " ".join(parts)
    tool_calls = getattr(msg, "tool_calls", None) or []
    extra = " ".join(f"{tc.get('name')}({tc.get('args')})" for tc in tool_calls)
    return f"{content} {extra}".strip()


def count_tokens(messages: Iterable[BaseMessage]) -> int:
    enc = _encoding()
    return sum(len(enc.encode(message_text(m))) for m in messages)
