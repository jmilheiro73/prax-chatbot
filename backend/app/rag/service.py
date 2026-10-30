"""Ingestão e busca (Aulas 14 a 16).

    upload -> 202 -> worker (chunking -> enriquecimento -> embedding) -> ready

Regras que vieram das aulas:
- Idempotência: mesmo nome e mesmo conteúdo não reprocessam.
- Só o que mudou gasta embedding: o hash por chunk é a ideia da Merkle tree do Cursor, sem a árvore.
- Busca por top-k sem threshold: a Praxis não usa, e um corte fixo já derrubou resposta certa.
- Enriquecimento é decisão de produto e custa uma chamada de LLM por chunk novo, então é opcional.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
from collections.abc import Awaitable, Callable

from langchain_core.embeddings import Embeddings

from app.rag.chunking import CHUNKER_VERSION, Chunk, chunk_document
from app.rag.store import ChunkRow, Document, KnowledgeStore
from app.rag.vector_index import VectorIndex, VectorItem, to_bytes

logger = logging.getLogger(__name__)

_NAMES_IN_CONTEXT = 10
# Recebe (texto do documento, chunk) e devolve o contexto curto que vai para o embedding.
Enricher = Callable[[str, Chunk], Awaitable[str]]


class DocumentNotFound(ValueError):
    pass


class KnowledgeService:
    def __init__(
        self,
        store: KnowledgeStore,
        index: VectorIndex,
        embeddings: Embeddings,
        embedding_model: str,
        top_k: int = 5,
        chunk_tokens: int = 400,
        enricher: Enricher | None = None,
    ):
        self._store = store
        self._index = index
        self._embeddings = embeddings
        self._embedding_model = embedding_model
        self._top_k = top_k
        self._chunk_tokens = chunk_tokens
        self._enricher = enricher
        self._queue: asyncio.Queue[str] = asyncio.Queue()
        self._worker: asyncio.Task | None = None

    async def start(self) -> None:
        await self._rebuild_index()
        for doc_id in await self._store.pending_ids():
            self._queue.put_nowait(doc_id)
        self._worker = asyncio.create_task(self._run(), name="knowledge-worker")

    async def stop(self) -> None:
        if self._worker:
            self._worker.cancel()
            await asyncio.gather(self._worker, return_exceptions=True)
            self._worker = None

    async def wait_until_idle(self) -> None:
        """Só os testes e as evals precisam: espera a fila esvaziar."""
        await self._queue.join()

    async def _rebuild_index(self) -> None:
        rows = [r for r in await self._store.all_chunks() if r.embedding_model == self._embedding_model]
        if await self._index.count() != len(rows):
            await self._index.upsert([VectorItem(r.id, r.doc_id, r.embedding) for r in rows], wait=False)
            logger.info("índice %s reconstruído com %d chunks", self._index.name, len(rows))

    async def submit(self, name: str, content: str) -> tuple[Document, bool]:
        """Devolve (documento, entrou na fila?). Conteúdo igual ao atual não entra."""
        content_hash = hashlib.sha256(content.encode()).hexdigest()
        current = await self._store.by_name(name)
        if current and current.content_hash == content_hash and current.status != "error":
            return current, False
        doc = await self._store.save_new_version(name, content, content_hash)
        self._queue.put_nowait(doc.id)
        return doc, True

    async def _run(self) -> None:
        while True:
            doc_id = await self._queue.get()
            try:
                await self._process(doc_id)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.exception("falha ao ingerir o documento %s", doc_id)
                await self._store.set_status(doc_id, "error", str(exc)[:500])
            finally:
                self._queue.task_done()

    async def _process(self, doc_id: str) -> None:
        doc = await self._store.get(doc_id)
        if doc is None:  # apagado enquanto esperava na fila
            return
        await self._store.set_status(doc_id, "chunking")
        text = await self._store.content_of(doc_id)
        chunks = chunk_document(text, self._chunk_tokens)
        if not chunks:
            raise ValueError("documento sem texto")

        previous = await self._store.chunks_of(doc_id)
        known = {r.hash: r for r in previous if r.embedding_model == self._embedding_model}
        new = [c for c in chunks if c.hash not in known]

        await self._store.set_status(doc_id, "embedding")
        contexts = await self._enrich(text, new)
        vectors = await self._embeddings.aembed_documents(
            [self._embedding_text(doc.name, c, contexts[c.hash]) for c in new]
        ) if new else []
        embedded = {c.hash: to_bytes(v) for c, v in zip(new, vectors)}

        rows = [
            ChunkRow(
                id=f"{doc_id}:{c.hash[:16]}:{c.order}",
                doc_id=doc_id,
                doc_name=doc.name,
                doc_order=c.order,
                section=c.section,
                content=c.content,
                context=known[c.hash].context if c.hash in known else contexts[c.hash],
                hash=c.hash,
                embedding=known[c.hash].embedding if c.hash in known else embedded[c.hash],
                embedding_model=self._embedding_model,
            )
            for c in chunks
        ]
        await self._store.replace_chunks(doc, rows, CHUNKER_VERSION, reused=len(chunks) - len(new))
        await self._index.delete([r.id for r in previous])
        await self._index.upsert([VectorItem(r.id, doc_id, r.embedding) for r in rows])
        await self._store.set_status(doc_id, "ready")  # por último: "pronto" tem de significar buscável

    async def _enrich(self, text: str, chunks: list[Chunk]) -> dict[str, str]:
        if not self._enricher:
            return {c.hash: "" for c in chunks}
        contexts = await asyncio.gather(*(self._enricher(text, c) for c in chunks))
        return {c.hash: context for c, context in zip(chunks, contexts)}

    @staticmethod
    def _embedding_text(doc_name: str, chunk: Chunk, context: str) -> str:
        return "\n".join(part for part in (doc_name, chunk.section, context, chunk.content) if part)

    async def list_documents(self) -> list[Document]:
        return await self._store.list_documents()

    async def delete(self, doc_id: str) -> bool:
        if await self._store.get(doc_id) is None:
            return False
        rows = await self._store.chunks_of(doc_id)
        await self._store.delete(doc_id)
        await self._index.delete([r.id for r in rows])
        return True

    async def search(self, query: str, document: str | None = None, k: int | None = None) -> list[dict]:
        """`document` aceita nome ou id. Filtro que não casa é erro: lista vazia faria o modelo dizer "não encontrei"."""
        scope = None
        if document:
            found = await self._store.by_name(document) or await self._store.get(document)
            if found is None:
                raise DocumentNotFound(f"documento não encontrado: {document}")
            scope = found.id
        vector = await self._embeddings.aembed_query(query)
        hits = await self._index.search(vector, k or self._top_k, scope=scope)
        rows = {r.id: r for r in await self._store.chunks_by_ids([h.id for h in hits])}
        return [self._as_result(rows[h.id], h.similarity) for h in hits if h.id in rows]

    async def read_around(self, chunk_id: str, radius: int = 1) -> list[dict]:
        """Os vizinhos do chunk: é o "abrir o trecho" do progressive disclosure."""
        found = await self._store.chunks_by_ids([chunk_id])
        if not found:
            return []
        rows = await self._store.neighbors(found[0].doc_id, found[0].doc_order, radius)
        return [self._as_result(r) for r in rows]

    async def status_line(self) -> str:
        """O `knowledge_status` do runtime context (Live 07). Com os nomes, o modelo sabe quando não precisa buscar."""
        docs = await self._store.list_documents()
        if not docs:
            return "nenhum"
        ready = [d.name for d in docs if d.status == "ready"]
        failed = sum(d.status == "error" for d in docs)
        pending = len(docs) - len(ready) - failed
        names = ", ".join(ready[:_NAMES_IN_CONTEXT]) + (" e outros" if len(ready) > _NAMES_IN_CONTEXT else "")
        parts = [f"{len(ready)} pronto(s): {names}"] if ready else []
        if pending:
            parts.append(f"{pending} processando")
        if failed:
            parts.append(f"{failed} com erro")
        return ", ".join(parts)

    @staticmethod
    def _as_result(row: ChunkRow, score: float | None = None) -> dict:
        result = {
            "chunk_id": row.id,
            "document": row.doc_name,
            "document_id": row.doc_id,
            "section": row.section,
            "text": row.content,
        }
        if score is not None:
            result["score"] = round(score, 3)
        return result
