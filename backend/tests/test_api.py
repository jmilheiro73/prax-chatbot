"""Rota HTTP (P1 · AC-01): chama o runner e devolve text/event-stream. Sem LangGraph aqui."""

from __future__ import annotations

import json
from types import SimpleNamespace

import httpx
from fastapi import FastAPI

from app.api.agent import router


def make_app(runner) -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    app.state.resources = SimpleNamespace(runner=runner)
    return app


async def test_execute_streams_sse(runner):
    app = make_app(runner)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        async with client.stream("POST", "/agent/execute", json={"message": "Qual o clima em São Paulo?"}) as r:
            assert r.status_code == 200
            assert r.headers["content-type"].startswith("text/event-stream")
            thread_id = r.headers["x-thread-id"]
            body = "".join([chunk async for chunk in r.aiter_text()])

    frames = [f for f in body.split("\n\n") if f.strip()]
    kinds = [f.split("\n", 1)[0].removeprefix("event: ") for f in frames]
    assert "on_tool_start" in kinds and "on_tool_end" in kinds and "on_chat_model_end" in kinds
    for f in frames:
        _, data = f.split("\n", 1)
        json.loads(data.removeprefix("data: "))  # todo frame é JSON válido

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        snap = (await client.get(f"/agent/threads/{thread_id}")).json()
    assert snap["checkpoint_alive"] and snap["messages"][0]["type"] == "human"


def test_http_layer_does_not_import_langgraph():
    import sys
    import app.api.agent as api  # noqa: F401
    src = open(api.__file__, encoding="utf-8").read()
    assert "langgraph" not in src and "langchain" not in src
    assert "app.api.agent" in sys.modules
