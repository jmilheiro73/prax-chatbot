"""Teste de fumaça (P1 · AC-08) + roteiro do D3, contra a API rodando em http://localhost:8000.

    uv run python smoke.py                 # AC-08: clima em São Paulo
    uv run python smoke.py d3              # D3: mensagem longa -> compacta -> lembra -> TTL

Imprime cada frame SSE resumido, o snapshot da thread e, no D3, espera o TTL expirar.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import uuid

import httpx

API = os.getenv("API_URL", "http://localhost:8000")


async def ask(client: httpx.AsyncClient, message: str, thread_id: str) -> str:
    print(f"\n>>> {message!r}")
    final = ""
    async with client.stream("POST", f"{API}/agent/execute", json={"message": message, "thread_id": thread_id}) as r:
        r.raise_for_status()
        buf = ""
        async for chunk in r.aiter_text():
            buf += chunk
            while "\n\n" in buf:
                frame, buf = buf.split("\n\n", 1)
                ev_line, data_line = frame.split("\n", 1)
                ev = json.loads(data_line.removeprefix("data: "))
                name = ev["event"]
                if name == "on_chat_model_stream":
                    print(ev["data"]["chunk"]["content"], end="", flush=True)
                elif name == "on_tool_start":
                    print(f"\n[tool start] {ev['name']}({ev['data']['input']})")
                elif name == "on_tool_end":
                    print(f"[tool end] {ev['data']['output']['content']}")
                elif name == "on_chat_model_end":
                    final = ev["data"]["output"]["content"] or final
                    print()
    return final


async def snapshot(client: httpx.AsyncClient, thread_id: str) -> dict:
    snap = (await client.get(f"{API}/agent/threads/{thread_id}")).json()
    print(f"[snapshot] checkpoint_alive={snap['checkpoint_alive']} messages={len(snap['messages'])} "
          f"summary={'sim' if snap['summary'] else 'não'}")
    if snap["summary"]:
        print("[summary]", snap["summary"])
    return snap


async def smoke() -> None:
    async with httpx.AsyncClient(timeout=120) as c:
        final = await ask(c, "Qual o clima em São Paulo?", str(uuid.uuid4()))
        assert "22" in final, "AC-08: a resposta deveria citar 22°C"
        print("\nOK · AC-08")


async def d3() -> None:
    ttl = int(os.getenv("CHECKPOINT_TTL_SECONDS", "60"))
    thread = str(uuid.uuid4())
    async with httpx.AsyncClient(timeout=120) as c:
        await ask(c, "Oi! Meu nome é Ana, sou advogada tributarista em Curitiba e estou montando um "
                     "chatbot para triagem de intimações. Prefiro respostas curtas.", thread)
        await snapshot(c, thread)
        await ask(c, "Qual é o meu nome e o que eu estou montando?", thread)   # dispara a compactação
        snap = await snapshot(c, thread)
        assert snap["summary"], "AC-03: deveria existir summary após a 2ª mensagem"
        print(f"\n[ttl] esperando {ttl + 5}s o checkpoint expirar no Redis…")
        await asyncio.sleep(ttl + 5)
        snap = await snapshot(c, thread)
        assert not snap["checkpoint_alive"], "AC-02: checkpoint deveria ter expirado"
        await ask(c, "Lembra onde eu moro?", thread)                          # só o summary responde
        print("\nOK · D3 — confira o trace no LangSmith: run 'summarize_conversation' e o system prompt do 'prax-chatbot' seguinte")


if __name__ == "__main__":
    asyncio.run(d3() if (sys.argv[1:] and sys.argv[1] == "d3") else smoke())
