"""Tools da base de conhecimento: progressive disclosure (Live 07).

Tools pequenas e componíveis, em vez de uma que já traz tudo: o catálogo, depois a busca, depois abrir o trecho.
O trecho volta como resultado de tool, nunca no system prompt: chunk é conteúdo não confiável.
"""

from __future__ import annotations

import json

from langchain_core.tools import BaseTool, tool

from app.rag.service import DocumentNotFound, KnowledgeService


def _as_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False)


def _list_documents(knowledge: KnowledgeService) -> BaseTool:
    @tool
    async def list_documents() -> str:
        """Lista os documentos do usuário: nome, status e número de trechos."""
        docs = await knowledge.list_documents()
        return _as_json([{"name": d.name, "status": d.status, "chunks": d.chunk_count} for d in docs])

    return list_documents


def _search_documents(knowledge: KnowledgeService) -> BaseTool:
    @tool
    async def search_documents(query: str, document: str | None = None) -> str:
        """Busca os trechos mais parecidos com a pergunta nos documentos do usuário.
        Sem `document`, busca em todos: é o normal. Passe o nome exato só para restringir a um documento.
        Cite o documento e a seção do trecho usado."""
        try:
            return _as_json(await knowledge.search(query, document))
        except DocumentNotFound as exc:
            return _as_json({"error": str(exc)})

    return search_documents


def _read_around(knowledge: KnowledgeService) -> BaseTool:
    @tool
    async def read_around(chunk_id: str) -> str:
        """Abre um trecho encontrado com os vizinhos dele. Use quando o trecho parecer cortado."""
        return _as_json(await knowledge.read_around(chunk_id))

    return read_around


def as_tools(ctx) -> list[BaseTool]:
    """As tools do orquestrador."""
    if ctx is None or ctx.knowledge is None:
        return []
    return [_list_documents(ctx.knowledge), _search_documents(ctx.knowledge)]


def specialist_tools(knowledge: KnowledgeService) -> list[BaseTool]:
    """As do subagente, que também pode abrir o trecho: filtrar tools por agente (Live 09)."""
    return [_list_documents(knowledge), _search_documents(knowledge), _read_around(knowledge)]
