"""Subagente (Aula 19): o orquestrador recebe `done` + resumo, e o miolo não aparece nem no contexto nem na tela."""

from __future__ import annotations

import json

from langchain_core.messages import ToolMessage


async def test_delegar_devolve_so_status_e_resumo(full_runner, fake_llm, knowledge):
    await knowledge.submit("manual.md", "# Manual\nO colaborador tem trinta dias de férias.\n")
    await knowledge.wait_until_idle()

    events = [e async for e in full_runner.stream("Pesquise a fundo as regras de férias", "t1")]

    tool_events = [e for e in events if e["event"].startswith("on_tool_")]
    assert [e["name"] for e in tool_events] == ["delegate_research", "delegate_research"]  # sem o search do especialista

    output = tool_events[-1]["data"]["output"]
    result = json.loads(output.content)
    assert result == {"status": "done", "summary": "Resumo do especialista.", "sources": ["doc"]}

    # O contexto do orquestrador só viu o resumo: nenhuma busca entrou no estado dele.
    state = (await full_runner._graph.aget_state(full_runner._config("t1"))).values["messages"]
    assert [m.name for m in state if isinstance(m, ToolMessage)] == ["delegate_research"]
    assert "Pesquisa: Resumo do especialista." in state[-1].content

    # Os tokens do especialista também não vão para a tela (AC-04).
    assert all(not (e.get("tags") or []) or "subagent" not in e["tags"] for e in events)


async def test_gasto_do_subagente_e_registrado_a_parte(full_runner, conversations, knowledge):
    await knowledge.submit("manual.md", "# Manual\nFérias.\n")
    await knowledge.wait_until_idle()
    _ = [e async for e in full_runner.stream("Pesquise a fundo as férias", "t1")]
    usage = (await conversations.metrics())["usage_by_purpose"]
    assert usage["subagent"]["calls"] >= 2 and usage["chat"]["calls"] == 2


async def test_busca_direta_nao_passa_pelo_subagente(full_runner, knowledge):
    await knowledge.submit("manual.md", "# Manual\nO colaborador tem trinta dias de férias.\n")
    await knowledge.wait_until_idle()
    events = [e async for e in full_runner.stream("O que o documento diz sobre férias?", "t1")]
    assert {e["name"] for e in events if e["event"] == "on_tool_end"} == {"search_documents"}
    assert "trinta dias" in events[-1]["data"]["output"].content


def test_modelo_so_ve_o_parametro_task():
    """O `config` é injetado pelo LangChain: se aparecesse no schema, o modelo teria de preenchê-lo."""
    from langchain_core.utils.function_calling import convert_to_openai_tool

    from app.agent.subagents import delegate_tool

    schema = convert_to_openai_tool(delegate_tool(subagent=None))
    assert list(schema["function"]["parameters"]["properties"]) == ["task"]

