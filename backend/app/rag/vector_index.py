"""Índice vetorial HNSW no Redis (Live 07): "HNSW é um grafo em camadas".

`m` são as conexões por nó e `ef_construction` o esforço ao inserir. Mais conexão melhora a busca e encarece a
inserção: foi assim o incidente da aula, que baixou `m` de 64 para 32.

O Redis aqui é efêmero (`docker-compose.yml`), então o índice não é fonte de verdade: os vetores também ficam no
SQLite, e o `rebuild` refaz o índice no boot sem chamar a API de embeddings de novo.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass

import numpy as np
from redisvl.index import AsyncSearchIndex
from redisvl.query import VectorQuery
from redisvl.query.filter import Tag
from redisvl.schema import IndexSchema

logger = logging.getLogger(__name__)
_SEARCHABLE_TIMEOUT_S = 2.0


@dataclass(frozen=True)
class VectorItem:
    id: str
    scope: str  # usado para filtrar antes de buscar: id do documento, ou usuário
    vector: bytes


@dataclass(frozen=True)
class VectorHit:
    id: str
    similarity: float


def to_bytes(vector: list[float]) -> bytes:
    return np.array(vector, dtype=np.float32).tobytes()


class VectorIndex:
    def __init__(self, name: str, dims: int, redis_url: str, m: int = 16, ef_construction: int = 64):
        # A dimensão entra no nome: trocar de modelo de embedding é outro índice, nunca uma mistura.
        self.name = f"{name}:{dims}"
        schema = IndexSchema.from_dict(
            {
                "index": {"name": self.name, "prefix": self.name, "storage_type": "hash"},
                "fields": [
                    {"name": "item_id", "type": "tag"},
                    {"name": "scope", "type": "tag"},
                    {
                        "name": "embedding",
                        "type": "vector",
                        "attrs": {
                            "dims": dims,
                            "distance_metric": "cosine",
                            "algorithm": "hnsw",
                            "datatype": "float32",
                            "m": m,
                            "ef_construction": ef_construction,
                        },
                    },
                ],
            }
        )
        self._index = AsyncSearchIndex(schema, redis_url=redis_url)

    async def open(self) -> "VectorIndex":
        """O `FT.CREATE` varre as chaves em segundo plano; busca nesse meio-tempo pode voltar vazia."""
        await self._index.create(overwrite=False)
        deadline = time.monotonic() + _SEARCHABLE_TIMEOUT_S
        while int((await self._index.info()).get("indexing", 0)) and time.monotonic() < deadline:
            await asyncio.sleep(0.005)
        return self

    async def close(self) -> None:
        await self._index.disconnect()

    async def drop(self) -> None:
        await self._index.delete(drop=True)

    async def count(self) -> int:
        return int((await self._index.info()).get("num_docs", 0))

    async def upsert(self, items: list[VectorItem], wait: bool = True) -> None:
        if not items:
            return
        await self._index.load(
            [{"item_id": i.id, "scope": i.scope, "embedding": i.vector} for i in items], id_field="item_id"
        )
        if wait:
            await self._wait_until_searchable(items)

    async def _wait_until_searchable(self, items: list[VectorItem]) -> None:
        """Com `search-workers` > 0 (o padrão do Redis 8), o HNSW indexa em segundo plano.

        A busca logo depois da escrita pode não ver o vetor: o documento pareceria pronto sem estar, e um fato
        repetido passaria pelo teste de duplicata. Por isso a escrita só termina quando o vetor aparece na busca.
        """
        deadline = time.monotonic() + _SEARCHABLE_TIMEOUT_S
        for item in items:
            query = VectorQuery(
                vector=item.vector,
                vector_field_name="embedding",
                return_fields=["item_id"],
                num_results=1,
                filter_expression=Tag("item_id") == item.id,
                dtype="float32",
            )
            while True:
                results = await self._index.query(query)
                if results and float(results[0]["vector_distance"]) < 1e-3:
                    break
                if time.monotonic() > deadline:
                    logger.warning("índice %s ainda sem o vetor %s; seguindo mesmo assim", self.name, item.id)
                    return
                await asyncio.sleep(0.005)

    async def delete(self, ids: list[str]) -> None:
        if ids:
            await self._index.drop_keys([self._index.key(i) for i in ids])

    async def search(self, vector: list[float], k: int, scope: str | None = None) -> list[VectorHit]:
        query = VectorQuery(
            vector=vector,
            vector_field_name="embedding",
            return_fields=["item_id"],
            num_results=k,
            filter_expression=(Tag("scope") == scope) if scope else None,
            dtype="float32",
        )
        results = await self._index.query(query)
        # A distância de cosseno vai de 0 a 2; similaridade é o que a aula e o threshold usam.
        return [VectorHit(id=r["item_id"], similarity=1 - float(r["vector_distance"])) for r in results]
