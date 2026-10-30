"""Embeddings falsos e determinísticos: saco de palavras com hash. Texto com palavra em comum fica perto.

Dá para testar recall e threshold sem chamar a OpenAI. `texts` guarda o que foi embedado, para contar gasto.
"""

from __future__ import annotations

import hashlib
import math
import re

from langchain_core.embeddings import Embeddings


class FakeEmbeddings(Embeddings):
    DIMS = 256

    def __init__(self) -> None:
        self.texts: list[str] = []

    def _vector(self, text: str) -> list[float]:
        self.texts.append(text)
        vector = [0.0] * self.DIMS
        for word in re.findall(r"\w+", text.lower()):
            vector[int(hashlib.md5(word.encode()).hexdigest(), 16) % self.DIMS] += 1.0
        norm = math.sqrt(sum(v * v for v in vector)) or 1.0
        return [v / norm for v in vector]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._vector(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._vector(text)
