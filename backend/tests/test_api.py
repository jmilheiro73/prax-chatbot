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
            # Os 3 headers do gabarito do P1.
            assert r.headers["cache-control"] == "no-cache"
            assert r.headers["connection"] == "keep-alive"
            assert r.headers["x-accel-buffering"] == "no"
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


def _full_app(full_runner, conversations, knowledge, memory) -> FastAPI:
    from app.api.knowledge import router as knowledge_router
    from app.api.memories import router as memories_router

    app = FastAPI()
    app.include_router(router)
    app.include_router(knowledge_router)
    app.include_router(memories_router)
    app.state.resources = SimpleNamespace(
        runner=full_runner, conversations=conversations, knowledge=knowledge, memory=memory
    )
    return app


async def test_rotas_de_conversa(full_runner, conversations, knowledge, memory):
    app = _full_app(full_runner, conversations, knowledge, memory)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        async with client.stream("POST", "/agent/execute", json={"message": "oi", "thread_id": "t1"}) as r:
            _ = [c async for c in r.aiter_text()]

        threads = (await client.get("/agent/threads")).json()["threads"]
        assert [t["thread_id"] for t in threads] == ["t1"]

        snap = (await client.get("/agent/threads/t1")).json()
        assert [m["type"] for m in snap["transcript"]] == ["human", "ai"]
        run_id = snap["transcript"][-1]["run_id"]

        assert (await client.post("/agent/threads/t1/feedback", json={"run_id": run_id, "value": "up"})).status_code == 204
        assert (await client.post("/agent/threads/t1/feedback", json={"run_id": "x", "value": "up"})).status_code == 404
        assert (await client.post("/agent/threads/t1/feedback", json={"run_id": run_id, "value": "ruim"})).status_code == 422
        assert (await client.get("/agent/metrics")).json()["feedback"]["up"] == 1

        assert (await client.delete("/agent/threads/t1")).status_code == 204
        assert (await client.delete("/agent/threads/t1")).status_code == 404
        assert (await client.get("/agent/threads")).json()["threads"] == []


async def test_rotas_de_documentos_e_memorias(full_runner, conversations, knowledge, memory):
    app = _full_app(full_runner, conversations, knowledge, memory)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        created = await client.post("/knowledge/documents", json={"name": "a.md", "content": "# A\ntexto\n"})
        assert created.status_code == 202 and created.json()["queued"] is True
        await knowledge.wait_until_idle()
        doc = (await client.get("/knowledge/documents")).json()["documents"][0]
        assert doc["status"] == "ready" and "content" not in doc
        repeated = await client.post("/knowledge/documents", json={"name": "a.md", "content": "# A\ntexto\n"})
        assert repeated.status_code == 202 and repeated.json()["queued"] is False
        assert (await client.post("/knowledge/documents", json={"name": "b.md", "content": ""})).status_code == 422
        assert (await client.delete(f"/knowledge/documents/{doc['id']}")).status_code == 204
        assert (await client.delete(f"/knowledge/documents/{doc['id']}")).status_code == 404

        memory_id = (await client.post("/memories", json={"content": "Gosta de surfe"})).json()["id"]
        assert (await client.get("/memories")).json()["memories"][0]["type"] == "fact"
        assert (await client.patch(f"/memories/{memory_id}", json={"content": "Gosta de xadrez"})).json()["content"] == "Gosta de xadrez"
        assert (await client.post("/memories", json={"type": "outro", "content": "x"})).status_code == 422
        assert (await client.delete(f"/memories/{memory_id}")).status_code == 204
        assert (await client.patch(f"/memories/{memory_id}", json={"content": "y"})).status_code == 404


def test_export_tracing_env_nao_sobrescreve_o_ambiente(monkeypatch):
    from app.settings import Settings

    monkeypatch.setenv("LANGSMITH_PROJECT", "do-terminal")
    monkeypatch.delenv("LANGSMITH_TRACING", raising=False)
    settings = Settings(_env_file=None, OPENAI_API_KEY="x", LANGSMITH_TRACING="true", LANGSMITH_PROJECT="do-env")
    settings.export_tracing_env()
    import os

    assert os.environ["LANGSMITH_TRACING"] == "true"
    assert os.environ["LANGSMITH_PROJECT"] == "do-terminal"
    monkeypatch.delenv("LANGSMITH_TRACING")
