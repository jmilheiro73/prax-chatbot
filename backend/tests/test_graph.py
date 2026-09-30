"""P1: fluxo modelo -> tool -> modelo, eventos v2, SSE. D3: sumarização e injeção no system prompt."""

from __future__ import annotations

import json

from app.agent.graph import SUMMARIZER_TAG
from app.api.agent import encode_sse
from tests.conftest import make_runner
from tests.fake_llm import SUMMARY_MARK


async def collect(runner, message: str, thread_id: str) -> list[dict]:
    return [ev async for ev in runner.stream(message, thread_id)]


async def test_weather_tool_roundtrip(runner):
    events = await collect(runner, "Qual o clima em São Paulo?", "t1")
    names = [e["event"] for e in events]

    # P1 · AC-04: só chat_model e tool; AC-03: a tool dispara e o modelo volta.
    assert set(names) <= {
        "on_chat_model_start", "on_chat_model_stream", "on_chat_model_end",
        "on_tool_start", "on_tool_end",
    }
    assert names.index("on_tool_start") < names.index("on_tool_end")
    tool_end = next(e for e in events if e["event"] == "on_tool_end")
    assert json.loads(tool_end["data"]["output"].content) == {
        "city": "São Paulo", "temp_c": 22, "condition": "parcialmente nublado",
    }

    # AC-07: tokens concatenam; o `end` daquela passada substitui o rascunho.
    last_end = [e for e in events if e["event"] == "on_chat_model_end"][-1]
    assert "22°C" in last_end["data"]["output"].content
    streamed = "".join(
        e["data"]["chunk"].content for e in events
        if e["event"] == "on_chat_model_stream" and e["run_id"] == last_end["run_id"]
    )
    assert streamed == last_end["data"]["output"].content


async def test_sse_encoding_uses_event_name_and_full_payload(runner):
    events = await collect(runner, "oi", "t2")
    frame = encode_sse(events[-1])
    head, _, body = frame.partition("\n")
    assert head == f"event: {events[-1]['event']}"
    assert body.startswith("data: ") and frame.endswith("\n\n")
    payload = json.loads(body[len("data: "):].strip())
    assert set(payload) >= {"event", "name", "run_id", "data"}  # o StreamEvent inteiro (AC-05)


async def test_checkpoint_remembers_within_thread(runner):
    await collect(runner, "meu nome é Ana", "t3")
    snap = await runner.snapshot("t3")
    assert snap.checkpoint_alive and len(snap.messages) == 2
    other = await runner.snapshot("t-other")
    assert not other.checkpoint_alive  # outra thread não vê nada


async def test_compaction_stores_summary_and_injects_it(fake_llm, summary_store):
    runner = make_runner(fake_llm, summary_store, token_limit=10, keep_last=0)
    thread = "t4"

    # Turno 1: histórico vazio -> nada a compactar; a mensagem longa entra no checkpoint.
    long_msg = "Meu nome é Ana e eu trabalho com direito tributário em Curitiba. " * 3
    events1 = await collect(runner, long_msg, thread)
    assert (await summary_store.get(thread)) is None
    assert "conversation_summary" not in (fake_llm.last_system_prompt or "")

    # Turno 2: histórico > 10 tokens -> compacta, grava, injeta no system prompt.
    events2 = await collect(runner, "qual é o meu nome?", thread)
    stored = await summary_store.get(thread)
    assert stored is not None and stored.summary.startswith(SUMMARY_MARK) and stored.compactions == 1
    assert "<conversation_summary>" in fake_llm.last_system_prompt
    assert stored.summary in fake_llm.last_system_prompt

    # As mensagens antigas saíram do estado; sobrou só o turno atual.
    snap = await runner.snapshot(thread)
    assert [m["type"] for m in snap.messages] == ["human", "ai"]
    assert snap.summary == stored.summary

    # O front nunca vê os tokens do resumo.
    assert all(SUMMARIZER_TAG not in (e.get("tags") or []) for e in events1 + events2)
    streamed = [e for e in events2 if e["event"] == "on_chat_model_stream"]
    assert streamed and all(SUMMARY_MARK not in str(e["data"]["chunk"].content) for e in streamed)

    # Turno 3: compacta de novo incorporando o resumo anterior.
    await collect(runner, "e onde eu trabalho?", thread)
    assert (await summary_store.get(thread)).compactions == 2


async def test_summary_survives_when_checkpoint_is_gone(fake_llm, summary_store):
    # Simula o TTL do Redis: mesmo store de summary, checkpointer novo (vazio).
    r1 = make_runner(fake_llm, summary_store, token_limit=10, keep_last=0)
    await collect(r1, "Meu nome é Ana e moro em Curitiba, gosto de café.", "t5")
    await collect(r1, "ok", "t5")
    assert (await summary_store.get("t5")) is not None

    r2 = make_runner(fake_llm, summary_store, token_limit=10, keep_last=0)  # checkpoint expirou
    assert not (await r2.snapshot("t5")).checkpoint_alive
    await collect(r2, "qual meu nome?", "t5")
    assert "<conversation_summary>" in fake_llm.last_system_prompt  # ainda lembra via summary
