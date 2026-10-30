"""MCP server (Live 09): a base de conhecimento exposta para Claude Code, Cursor e afins.

É JSON-RPC 2.0 por POST, escrito à mão para o protocolo ficar à vista. Só leitura.
- A tool é `name` + `description` + `inputSchema`, e a description é o que faz o modelo chamar.
- O token aqui não é a chave da OpenAI: quem conecta nunca recebe credencial de dentro (sem token passthrough).
- Sem `MCP_SERVER_TOKEN` a rota não existe na prática. OAuth só faria sentido fora do localhost.
"""

from __future__ import annotations

import json
import secrets
from typing import Any, Awaitable, Callable

from fastapi import APIRouter, Request, Response, status
from fastapi.responses import JSONResponse

from app.rag.service import KnowledgeService

router = APIRouter(tags=["mcp"])

_SUPPORTED_VERSIONS = ("2025-06-18", "2025-03-26", "2024-11-05")
_SERVER_INFO = {"name": "prax-chatbot", "version": "0.1.0"}

_TOOLS = [
    {
        "name": "list_documents",
        "description": "Lista os documentos da base de conhecimento do Prax: nome, status e número de trechos.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "search_documents",
        "description": "Busca, por similaridade, os trechos mais parecidos com a pergunta na base de conhecimento do "
        "Prax. Devolve documento, seção e texto de cada trecho.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "A pergunta, em linguagem natural."},
                "document": {"type": "string", "description": "Opcional: nome de um documento, para buscar só nele."},
            },
            "required": ["query"],
            "additionalProperties": False,
        },
    },
]


async def _list_documents(knowledge: KnowledgeService, _: dict[str, Any]) -> Any:
    docs = await knowledge.list_documents()
    return [{"name": d.name, "status": d.status, "chunks": d.chunk_count} for d in docs]


async def _search_documents(knowledge: KnowledgeService, args: dict[str, Any]) -> Any:
    query = args.get("query")
    if not isinstance(query, str) or not query.strip():
        raise ValueError("`query` é obrigatório")
    return await knowledge.search(query, args.get("document"))


_HANDLERS: dict[str, Callable[[KnowledgeService, dict[str, Any]], Awaitable[Any]]] = {
    "list_documents": _list_documents,
    "search_documents": _search_documents,
}


def _result(request_id: Any, result: dict[str, Any]) -> JSONResponse:
    return JSONResponse({"jsonrpc": "2.0", "id": request_id, "result": result})


def _error(request_id: Any, code: int, message: str) -> JSONResponse:
    return JSONResponse({"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}})


@router.post("/mcp")
async def mcp(request: Request) -> Response:
    resources = request.app.state.resources
    token = resources.settings.mcp_server_token
    if not token:
        return Response(status_code=status.HTTP_404_NOT_FOUND)
    # compare_digest: comparar segredo com `==` vaza o tamanho do prefixo certo pelo tempo de resposta.
    if not secrets.compare_digest(request.headers.get("authorization", ""), f"Bearer {token}"):
        return Response(status_code=status.HTTP_401_UNAUTHORIZED, headers={"WWW-Authenticate": "Bearer"})

    try:
        body = json.loads(await request.body())
    except ValueError:
        return _error(None, -32700, "JSON inválido")
    if not isinstance(body, dict):
        return _error(None, -32600, "requisição inválida")

    method, request_id, params = body.get("method"), body.get("id"), body.get("params") or {}
    if request_id is None:  # notificação não tem resposta
        return Response(status_code=status.HTTP_202_ACCEPTED)

    if method == "initialize":
        asked = params.get("protocolVersion")
        return _result(
            request_id,
            {
                "protocolVersion": asked if asked in _SUPPORTED_VERSIONS else _SUPPORTED_VERSIONS[0],
                "capabilities": {"tools": {}},
                "serverInfo": _SERVER_INFO,
            },
        )
    if method == "ping":
        return _result(request_id, {})
    if method == "tools/list":
        return _result(request_id, {"tools": _TOOLS})
    if method == "tools/call":
        handler = _HANDLERS.get(params.get("name"))
        if handler is None:
            return _error(request_id, -32602, f"tool desconhecida: {params.get('name')}")
        # Erro de execução vai no resultado, com `isError`: o modelo precisa ler e poder corrigir a chamada.
        try:
            output = await handler(resources.knowledge, params.get("arguments") or {})
        except ValueError as exc:
            return _result(request_id, {"content": [{"type": "text", "text": str(exc)}], "isError": True})
        text = json.dumps(output, ensure_ascii=False)
        return _result(request_id, {"content": [{"type": "text", "text": text}], "isError": False})
    return _error(request_id, -32601, f"método desconhecido: {method}")
