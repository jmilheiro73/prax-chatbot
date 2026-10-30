"""MCP client escrito à mão (Live 09): para ver o protocolo, que é JSON-RPC sobre HTTP.

- `tools/list` roda uma vez, ao conectar, e fica em cache.
- Cada servidor tem uma lista de globs: expor 3 mil tools ao modelo lota o contexto, então o agente vê só as que
  casam (`list_jobs*`, no case da aula).
- A `description` vem do servidor e você não a controla: entra no prompt do modelo. Só conecte servidor confiável.

Desligado por padrão: o chat tem escopo fechado, e a aula diz que aí MCP não é necessário. Sem OAuth: só bearer fixo.
"""

from __future__ import annotations

import fnmatch
import json
import logging
from dataclasses import dataclass, field
from typing import Any

import httpx
from langchain_core.tools import BaseTool, StructuredTool

logger = logging.getLogger(__name__)
_PROTOCOL_VERSION = "2025-06-18"


@dataclass(frozen=True)
class McpServerConfig:
    name: str
    url: str
    token: str | None = None
    allow: list[str] = field(default_factory=lambda: ["*"])


class McpError(RuntimeError):
    pass


class McpClient:
    def __init__(self, config: McpServerConfig, http: httpx.AsyncClient):
        self._config = config
        self._http = http
        self._next_id = 0
        self._session_id: str | None = None

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json, text/event-stream", "MCP-Protocol-Version": _PROTOCOL_VERSION}
        if self._config.token:
            headers["Authorization"] = f"Bearer {self._config.token}"
        if self._session_id:
            headers["Mcp-Session-Id"] = self._session_id
        return headers

    async def _rpc(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        self._next_id += 1
        response = await self._http.post(
            self._config.url,
            json={"jsonrpc": "2.0", "id": self._next_id, "method": method, "params": params or {}},
            headers=self._headers(),
        )
        response.raise_for_status()
        self._session_id = response.headers.get("Mcp-Session-Id", self._session_id)
        body = _parse_body(response)
        if "error" in body:
            raise McpError(f"{method}: {body['error'].get('message')}")
        return body["result"]

    async def connect(self) -> list[dict[str, Any]]:
        """O handshake, e o `tools/list` que fica em cache enquanto o app estiver no ar."""
        await self._rpc(
            "initialize",
            {
                "protocolVersion": _PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "prax-chatbot", "version": "0.1.0"},
            },
        )
        await self._http.post(
            self._config.url, json={"jsonrpc": "2.0", "method": "notifications/initialized"}, headers=self._headers()
        )
        tools = (await self._rpc("tools/list"))["tools"]
        return [t for t in tools if any(fnmatch.fnmatch(t["name"], g) for g in self._config.allow)]

    async def call(self, name: str, arguments: dict[str, Any]) -> str:
        result = await self._rpc("tools/call", {"name": name, "arguments": arguments})
        text = "\n".join(block.get("text", "") for block in result.get("content", []) if block.get("type") == "text")
        return f"erro da tool: {text}" if result.get("isError") else text


def _parse_body(response: httpx.Response) -> dict[str, Any]:
    """Um servidor pode responder JSON ou um stream SSE com a resposta dentro."""
    if response.headers.get("content-type", "").startswith("text/event-stream"):
        for line in response.text.splitlines():
            if line.startswith("data:"):
                return json.loads(line[5:])
        raise McpError("resposta SSE sem dados")
    return response.json()


def _as_langchain_tool(client: McpClient, server: str, definition: dict[str, Any]) -> BaseTool:
    name = definition["name"]

    async def call(**arguments: Any) -> str:
        return await client.call(name, arguments)

    return StructuredTool.from_function(
        coroutine=call,
        # O prefixo evita colisão entre servidores (a OpenAI aceita só letras, números, _ e -).
        name=f"{server}__{name}",
        description=definition.get("description", name),
        args_schema=definition.get("inputSchema") or {"type": "object", "properties": {}},
    )


async def load_mcp_tools(servers: list[McpServerConfig], http: httpx.AsyncClient) -> list[BaseTool]:
    tools: list[BaseTool] = []
    for config in servers:
        client = McpClient(config, http)
        try:
            definitions = await client.connect()
        except (httpx.HTTPError, McpError, KeyError, ValueError):
            # Um servidor externo fora do ar não pode derrubar o chat.
            logger.exception("MCP server %s indisponível; seguindo sem as tools dele", config.name)
            continue
        logger.info("MCP server %s: %d tool(s)", config.name, len(definitions))
        tools.extend(_as_langchain_tool(client, config.name, d) for d in definitions)
    return tools
