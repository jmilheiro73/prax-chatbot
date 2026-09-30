"""O grafo do agente.

    START -> compact -> model -> (tools -> model)* -> END

- `compact`  (D3 · AC-03): se o histórico passou do limite, gera o summary (LLM), grava na
             SummaryStore (longo prazo) e REMOVE as mensagens antigas do estado.
- `model`    (P1 · AC-03): chama a LLM com o system prompt (+ summary no slot) e as mensagens.
- `tools`    (P1 · AC-03): executa a tool pedida e volta para o modelo.

Quem compila o grafo é o agente (P1 · AC-02): a camada HTTP nunca vê nada disto.
"""

from __future__ import annotations

from typing import Annotated, TypedDict

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    RemoveMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph, add_messages
from langgraph.prebuilt import ToolNode, tools_condition

from app.agent.prompts import SUMMARIZE_PROMPT, build_system_prompt
from app.agent.tokens import count_tokens, message_text
from app.memory.summary_store import SummaryStore

SUMMARIZER_TAG = "summarizer"  # o runner filtra estes eventos do stream do front
GRAPH_NAME = "praxis-chatbot"


class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    # Cópia do summary vigente. A fonte de verdade durável é a SummaryStore; aqui é só
    # para o nó `model` não bater no banco a cada turno e para o snapshot da thread.
    summary: str


class CompactionPolicy:
    def __init__(self, token_limit: int, keep_last: int):
        self.token_limit = token_limit
        self.keep_last = max(0, keep_last)

    def split(self, messages: list[BaseMessage]) -> tuple[list[BaseMessage], list[BaseMessage]]:
        """Divide em (a compactar, a manter). A última mensagem é sempre a humana da vez: fica."""
        history, current = messages[:-1], messages[-1:]
        if count_tokens(history) <= self.token_limit:
            return [], messages
        # Nunca deixa um ToolMessage órfão: se a fronteira cair depois de um AIMessage com tool
        # call, recua até uma HumanMessage/AIMessage sem tool_calls.
        cut = max(0, len(history) - self.keep_last)
        while cut > 0 and cut < len(history) and isinstance(history[cut], ToolMessage):
            cut -= 1
        return history[:cut], history[cut:] + current


def _thread_id(config: RunnableConfig) -> str:
    return str(config.get("configurable", {}).get("thread_id", "default"))


def _transcript(messages: list[BaseMessage]) -> str:
    lines = []
    for m in messages:
        role = {"human": "Usuário", "ai": "Assistente", "tool": "Ferramenta"}.get(m.type, m.type)
        lines.append(f"{role}: {message_text(m)}")
    return "\n".join(lines)


def build_graph(
    llm: BaseChatModel,
    tools: list[BaseTool],
    summary_store: SummaryStore,
    policy: CompactionPolicy,
    checkpointer: BaseCheckpointSaver | None = None,
):
    model_with_tools = llm.bind_tools(tools)
    # Nome e tag: é assim que se acha o prompt do summary no LangSmith (AC-04) e é a tag
    # que o runner usa para não streamar os tokens do resumo para o front.
    summarizer = llm.with_config(run_name="summarize_conversation", tags=[SUMMARIZER_TAG])

    async def compact(state: AgentState, config: RunnableConfig) -> dict:
        thread_id = _thread_id(config)
        messages = state["messages"]
        stored = await summary_store.get(thread_id)
        previous = stored.summary if stored else ""

        to_compact, _ = policy.split(messages)
        if not to_compact:
            # Checkpoint pode ter expirado (TTL) e o summary continuar no banco: recarrega.
            return {"summary": previous} if previous != state.get("summary", "") else {}

        prompt = SUMMARIZE_PROMPT.format(
            previous_summary=previous or "(nenhum)",
            transcript=_transcript(to_compact),
        )
        result = await summarizer.ainvoke([HumanMessage(content=prompt)])
        summary = result.content if isinstance(result.content, str) else message_text(result)
        await summary_store.upsert(thread_id, summary)
        return {
            "summary": summary,
            "messages": [RemoveMessage(id=m.id) for m in to_compact if m.id],
        }

    async def model(state: AgentState) -> dict:
        system = SystemMessage(content=build_system_prompt(state.get("summary")))
        response: AIMessage = await model_with_tools.ainvoke([system, *state["messages"]])
        return {"messages": [response]}

    graph = StateGraph(AgentState)
    graph.add_node("compact", compact)
    graph.add_node("model", model)
    graph.add_node("tools", ToolNode(tools))
    graph.add_edge(START, "compact")
    graph.add_edge("compact", "model")
    graph.add_conditional_edges("model", tools_condition, {"tools": "tools", END: END})
    graph.add_edge("tools", "model")
    return graph.compile(checkpointer=checkpointer, name=GRAPH_NAME)
