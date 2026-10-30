"""Subagente de pesquisa (Aula 19): o orquestrador delega e recebe só `done` + resumo.

    START -> model -> (tools -> model)* -> report -> END

O que o torna um subagente, e não mais um nó:
- Prompt próprio: assume que recebeu um pedaço e só para quando terminar.
- Tools próprias: `read_around` só existe aqui.
- Modelo próprio: `SUBAGENT_MODEL`, se configurado.
- Descartável: `checkpointer=False`, nada dele fica no estado do orquestrador.

O ganho é de contexto: as buscas não entram no histórico da conversa, só o resumo. É tarefa que se decompõe, então
é subagente. Multiagente só valeria com vários donos colaborando.
"""

from __future__ import annotations

import json
from typing import Annotated, TypedDict

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool, tool
from langgraph.graph import END, START, StateGraph, add_messages
from langgraph.prebuilt import ToolNode, tools_condition

from app.agent.prompts import REPORT_PROMPT, SPECIALIST_PROMPT
from app.agent.schemas import TaskResult
from app.memory.conversation_store import ConversationStore

SUBAGENT_TAG = "subagent"  # o runner filtra estes eventos do stream do front, como os do summarizer
_RECURSION_LIMIT = 12


class _SubagentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    result: dict


def build_research_subagent(llm: BaseChatModel, tools: list[BaseTool]):
    model_with_tools = llm.bind_tools(tools)
    reporter = llm.with_structured_output(TaskResult, include_raw=True)

    async def model(state: _SubagentState) -> dict:
        response = await model_with_tools.ainvoke([SystemMessage(content=SPECIALIST_PROMPT), *state["messages"]])
        return {"messages": [response]}

    async def report(state: _SubagentState) -> dict:
        result = await reporter.ainvoke([*state["messages"], HumanMessage(content=REPORT_PROMPT)])
        parsed: TaskResult | None = result["parsed"]
        if parsed is None:
            return {"result": {"status": "blocked", "summary": "O especialista não conseguiu relatar.", "sources": []}}
        return {"result": parsed.model_dump(exclude={"reasoning"}), "messages": [result["raw"]]}

    graph = StateGraph(_SubagentState)
    graph.add_node("model", model)
    graph.add_node("tools", ToolNode(tools))
    graph.add_node("report", report)
    graph.add_edge(START, "model")
    graph.add_conditional_edges("model", tools_condition, {"tools": "tools", END: "report"})
    graph.add_edge("tools", "model")
    graph.add_edge("report", END)
    return graph.compile(checkpointer=False, name="research_subagent")


def delegate_tool(subagent, conversations: ConversationStore | None = None) -> BaseTool:
    @tool("delegate_research")
    async def delegate_research(task: str, config: RunnableConfig) -> str:
        """Delega uma pesquisa ampla nos documentos a um especialista, que devolve só status e resumo.
        Use para comparar, consolidar ou cruzar vários trechos. Para achar um trecho só, prefira `search_documents`."""
        state = await subagent.ainvoke(
            {"messages": [HumanMessage(content=task)]},
            config={"tags": [SUBAGENT_TAG], "recursion_limit": _RECURSION_LIMIT, "run_name": "research_subagent"},
        )
        if conversations:
            thread_id = config.get("configurable", {}).get("thread_id")
            for message in state["messages"]:
                if isinstance(message, AIMessage):
                    await conversations.record_usage(thread_id, "subagent", message.usage_metadata)
        return json.dumps(state["result"], ensure_ascii=False)

    return delegate_research
