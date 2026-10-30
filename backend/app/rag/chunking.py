"""Chunking (Aula 14): por estrutura quando o formato é conhecido, recursivo por tokens para o resto.

Markdown vira seções pelos títulos. O caminho do título ("Guia > Instalação") fica como metadado do chunk,
que é enriquecimento determinístico: barato e confiável. Seção maior que o limite passa pelo recursivo, sem
overlap (400 tokens é o default forte do paper da Chroma, citado na aula).
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from app.agent.tokens import count_text_tokens, encoding

CHUNKER_VERSION = "md-recursive-1"
_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
_FENCE = re.compile(r"^\s*(```|~~~)")
_SEPARATORS = ("\n\n", "\n", ". ", " ")


@dataclass(frozen=True)
class Chunk:
    order: int
    section: str
    content: str
    hash: str


def _sections(text: str) -> list[tuple[str, str]]:
    """Divide em (caminho do título, corpo). Título dentro de bloco de código não conta."""
    sections: list[tuple[str, str]] = []
    path: list[tuple[int, str]] = []
    body: list[str] = []
    fenced = False

    def flush() -> None:
        content = "\n".join(body).strip()
        if content:
            sections.append((" > ".join(title for _, title in path), content))
        body.clear()

    for line in text.splitlines():
        if _FENCE.match(line):
            fenced = not fenced
        heading = None if fenced else _HEADING.match(line)
        if heading:
            flush()
            level = len(heading.group(1))
            path = [item for item in path if item[0] < level] + [(level, heading.group(2))]
        else:
            body.append(line)
    flush()
    return sections


def _split(text: str, max_tokens: int, separators: tuple[str, ...] = _SEPARATORS) -> list[str]:
    if count_text_tokens(text) <= max_tokens:
        return [text]
    for i, sep in enumerate(separators):
        if sep not in text:
            continue
        pieces: list[str] = []
        current = ""
        for part in text.split(sep):
            candidate = f"{current}{sep}{part}" if current else part
            if count_text_tokens(candidate) <= max_tokens:
                current = candidate
                continue
            if current:
                pieces.append(current)
            if count_text_tokens(part) > max_tokens:
                pieces.extend(_split(part, max_tokens, separators[i + 1:]))
                current = ""
            else:
                current = part
        if current:
            pieces.append(current)
        return pieces
    # Texto sem nenhum separador: só resta cortar por token.
    ids = encoding().encode(text)
    return [encoding().decode(ids[i : i + max_tokens]) for i in range(0, len(ids), max_tokens)]


def chunk_document(text: str, max_tokens: int = 400) -> list[Chunk]:
    chunks: list[Chunk] = []
    for section, body in _sections(text):
        for piece in _split(body, max_tokens):
            content = piece.strip()
            if content:
                digest = hashlib.sha256(f"{section}\n{content}".encode()).hexdigest()
                chunks.append(Chunk(order=len(chunks), section=section, content=content, hash=digest))
    return chunks
