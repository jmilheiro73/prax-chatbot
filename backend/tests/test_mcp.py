"""MCP (Live 09): o nosso server e o nosso client conversando pelo JSON-RPC real, sem rede."""

from __future__ import annotations

import json
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI

from app.agent.tools.mcp_client import McpClient, McpServerConfig, load_mcp_tools
from app.api.mcp import router

URL = "http://test/mcp"
TOKEN = "token-do-mcp"


@pytest.fixture
async def http(knowledge):
    await knowledge.submit("manual.md", "# Manual\nO colaborador tem trinta dias de férias.\n")
    await knowledge.wait_until_idle()
    app = FastAPI()
    app.include_router(router)
    app.state.resources = SimpleNamespace(settings=SimpleNamespace(mcp_server_token=TOKEN), knowledge=knowledge)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app)) as client:
        yield client


def _rpc(method: str, params: dict | None = None, id: int | None = 1) -> dict:
    body = {"jsonrpc": "2.0", "method": method, "params": params or {}}
    return {**body, "id": id} if id is not None else body


AUTH = {"Authorization": f"Bearer {TOKEN}"}


async def test_sem_token_da_401_com_www_authenticate(http):
    response = await http.post(URL, json=_rpc("tools/list"))
    assert response.status_code == 401 and response.headers["www-authenticate"] == "Bearer"
    response = await http.post(URL, json=_rpc("tools/list"), headers={"Authorization": "Bearer errado"})
    assert response.status_code == 401


async def test_sem_token_configurado_a_rota_nao_existe(knowledge):
    app = FastAPI()
    app.include_router(router)
    app.state.resources = SimpleNamespace(settings=SimpleNamespace(mcp_server_token=""), knowledge=knowledge)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app)) as client:
        assert (await client.post(URL, json=_rpc("tools/list"), headers=AUTH)).status_code == 404


async def test_handshake_e_tools_list(http):
    body = (await http.post(URL, json=_rpc("initialize", {"protocolVersion": "2025-03-26"}), headers=AUTH)).json()
    assert body["result"]["protocolVersion"] == "2025-03-26"
    assert body["result"]["capabilities"] == {"tools": {}}

    body = (await http.post(URL, json=_rpc("initialize", {"protocolVersion": "1999-01-01"}), headers=AUTH)).json()
    assert body["result"]["protocolVersion"] == "2025-06-18"

    notification = await http.post(URL, json=_rpc("notifications/initialized", id=None), headers=AUTH)
    assert notification.status_code == 202

    tools = (await http.post(URL, json=_rpc("tools/list"), headers=AUTH)).json()["result"]["tools"]
    assert {t["name"] for t in tools} == {"list_documents", "search_documents"}
    assert all({"name", "description", "inputSchema"} <= set(t) for t in tools)


async def test_erros_do_protocolo(http):
    assert (await http.post(URL, content="{", headers=AUTH)).json()["error"]["code"] == -32700
    assert (await http.post(URL, json=_rpc("nada"), headers=AUTH)).json()["error"]["code"] == -32601
    unknown = await http.post(URL, json=_rpc("tools/call", {"name": "nada"}), headers=AUTH)
    assert unknown.json()["error"]["code"] == -32602
    bad_args = await http.post(URL, json=_rpc("tools/call", {"name": "search_documents"}), headers=AUTH)
    assert bad_args.json()["result"]["isError"] is True


async def test_client_conecta_e_chama_o_server(http):
    client = McpClient(McpServerConfig("prax", URL, TOKEN), http)
    definitions = await client.connect()
    assert {d["name"] for d in definitions} == {"list_documents", "search_documents"}
    hits = json.loads(await client.call("search_documents", {"query": "dias de férias"}))
    assert "trinta dias" in hits[0]["text"]


async def test_glob_filtra_as_tools_que_o_agente_ve(http):
    tools = await load_mcp_tools([McpServerConfig("prax", URL, TOKEN, allow=["search_*"])], http)
    assert [t.name for t in tools] == ["prax__search_documents"]
    assert "similaridade" in tools[0].description

    output = await tools[0].ainvoke({"query": "dias de férias"})
    assert "trinta dias" in json.loads(output)[0]["text"]


async def test_server_fora_do_ar_nao_derruba_o_boot(http):
    assert await load_mcp_tools([McpServerConfig("prax", URL, "token-errado")], http) == []
