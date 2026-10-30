"""Transcript durável (Aula 11): a tela sobrevive ao TTL e à compactação. Mais o cancelamento e o gasto."""

from __future__ import annotations

from langchain_core.messages import AIMessage, ToolMessage

from app.agent.graph import orphan_tool_calls
from tests.conftest import make_runner


async def _drain(runner, message: str, thread_id: str) -> list[dict]:
    return [e async for e in runner.stream(message, thread_id)]


async def test_transcript_grava_so_o_evento_terminal(full_runner, conversations):
    await _drain(full_runner, "Qual o clima em São Paulo?", "t1")
    rows = await conversations.transcript("t1")
    assert [r["type"] for r in rows] == ["human", "ai", "tool", "ai"]
    assert rows[1]["tool_calls"][0]["name"] == "get_weather"
    assert "22" in rows[2]["content"] and rows[2]["tool_call_id"] == rows[1]["tool_calls"][0]["id"]
    assert "22°C" in rows[3]["content"]
    assert rows[3]["usage"]["output_tokens"] == 5
    assert rows[3]["run_id"]


async def test_transcript_sobrevive_a_compactacao(fake_llm, summary_store, conversations):
    runner = make_runner(fake_llm, summary_store, token_limit=1, keep_last=0, conversations=conversations)
    await _drain(runner, "primeira mensagem longa o bastante", "t1")
    await _drain(runner, "segunda mensagem", "t1")

    snap = await runner.snapshot("t1")
    assert len(snap.messages) == 2  # o checkpoint compactou
    assert [m["content"] for m in snap.transcript if m["type"] == "human"] == [
        "primeira mensagem longa o bastante",
        "segunda mensagem",
    ]


async def test_lista_titulo_e_tombstone(full_runner, conversations):
    await _drain(full_runner, "Primeira linha\nsegunda linha", "t1")
    assert (await conversations.get("t1")).title == "Primeira linha"

    await full_runner._background.drain()
    assert (await conversations.list_recent())[0].title == "Título da fake"

    assert await conversations.soft_delete("t1")
    assert await conversations.list_recent() == []
    assert len(await conversations.transcript("t1")) == 2  # tombstone não apaga o histórico
    assert not await conversations.soft_delete("t1")

    await _drain(full_runner, "voltei", "t1")
    assert len(await conversations.list_recent()) == 1


async def test_titulo_so_e_gerado_uma_vez(full_runner, fake_llm):
    await _drain(full_runner, "oi", "t1")
    await full_runner._background.drain()
    await _drain(full_runner, "oi de novo", "t1")
    await full_runner._background.drain()
    assert sum("Dê um título" in p for p in fake_llm.structured_prompts) == 1


async def test_feedback_e_metricas(full_runner, conversations):
    await _drain(full_runner, "Qual o clima em São Paulo?", "t1")
    await full_runner._background.drain()
    run_id = (await conversations.transcript("t1"))[-1]["run_id"]

    assert await conversations.set_feedback("t1", run_id, "down")
    assert not await conversations.set_feedback("t1", "outro-run", "up")
    assert (await conversations.transcript("t1"))[-1]["feedback"] == "down"

    metrics = await conversations.metrics()
    assert metrics["feedback"] == {"up": 0, "down": 1}
    assert metrics["answers"] == 2 and metrics["tool_results"] == 1 and metrics["tool_errors"] == 0
    assert metrics["usage_by_purpose"]["chat"]["calls"] == 2
    assert metrics["usage_by_purpose"]["title"]["calls"] == 1

    rated = await conversations.rated_down()
    assert rated[0]["question"] == "Qual o clima em São Paulo?" and "22°C" in rated[0]["answer"]


def test_orphan_tool_calls_acha_a_call_sem_resultado():
    answered = AIMessage(content="", id="a1", tool_calls=[{"name": "x", "args": {}, "id": "c1", "type": "tool_call"}])
    result = ToolMessage(content="ok", tool_call_id="c1", id="t1")
    orphan = AIMessage(content="", id="a2", tool_calls=[{"name": "x", "args": {}, "id": "c2", "type": "tool_call"}])
    assert orphan_tool_calls([answered, result]) == []
    assert orphan_tool_calls([answered, result, orphan]) == [orphan]


async def test_cancelar_no_meio_da_tool_nao_quebra_o_proximo_turno(fake_llm, summary_store, conversations):
    runner = make_runner(fake_llm, summary_store, conversations=conversations)
    stream = runner.stream("Qual o clima em São Paulo?", "t1")
    async for event in stream:
        if event["event"] == "on_tool_start":
            break
    await stream.aclose()  # é o que o Starlette faz quando o cliente fecha a conexão

    await _drain(runner, "E agora, tudo certo?", "t1")
    sent = fake_llm.calls[-1]
    assert not any(isinstance(m, AIMessage) and m.tool_calls for m in sent)
    assert orphan_tool_calls((await runner._graph.aget_state(runner._config("t1"))).values["messages"]) == []
    assert "eco" in (await conversations.transcript("t1"))[-1]["content"]


async def test_turno_cancelado_nao_dispara_o_pos_turno(full_runner, fake_llm):
    stream = full_runner.stream("Qual o clima em São Paulo?", "t1")
    async for event in stream:
        if event["event"] == "on_tool_start":
            break
    await stream.aclose()
    await full_runner._background.drain()
    assert fake_llm.structured_prompts == []


async def test_runtime_context_entra_no_system_prompt(fake_llm, summary_store):
    async def runtime():
        return {"agora": "2026-10-30 10:00", "documentos": "vazia"}

    runner = make_runner(fake_llm, summary_store, runtime_context=runtime)
    await _drain(runner, "oi", "t1")
    assert "<runtime_context>" in fake_llm.last_system_prompt
    assert "agora: 2026-10-30 10:00" in fake_llm.last_system_prompt
