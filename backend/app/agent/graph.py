"""O grafo do agente.

    START -> compact -> recall -> model -> (tools -> model)* -> END

- `compact`  (D3 · AC-03): se o histórico passou do limite, gera o summary (LLM), grava na
             SummaryStore (longo prazo) e REMOVE as mensagens antigas do estado.
- `recall`   (Aula 11): busca as memórias relevantes para este turno. Só existe se houver `memory`.
- `model`    (P1 · AC-03): chama a LLM com o system prompt (+ slots) e as mensagens.
- `tools`    (P1 · AC-03): executa a tool pedida e volta para o modelo.

Quem compila o grafo é o agente (P1 · AC-02): a camada HTTP nunca vê nada disto.
"""

from __future__ import annotations

from typing import Annotated, Awaitable, Callable, TypedDict

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
from app.memory.conversation_store import ConversationStore
from app.memory.service import MemoryService
from app.memory.summary_store import SummaryStore

SUMMARIZER_TAG = "summarizer"  # o runner filtra estes eventos do stream do front
GRAPH_NAME = "prax-chatbot"


class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    # Cópia do summary vigente. A fonte de verdade durável é a SummaryStore; aqui é só
    # para o nó `model` não bater no banco a cada turno e para o snapshot da thread.
    summary: str
    # O recorte de memória deste turno. Vem da busca, não é fonte de verdade.
    memories: list[str]


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


def orphan_tool_calls(messages: list[BaseMessage]) -> list[BaseMessage]:
    """Tool call sem resultado, com o que tiver respondido a ela (Aula 02: o par é sagrado).

    Sobra uma quando o usuário cancela no meio da tool. Mandar isso à OpenAI dá erro 400 no turno seguinte.
    """
    answered = {m.tool_call_id for m in messages if isinstance(m, ToolMessage)}
    orphans: list[BaseMessage] = []
    for m in messages:
        if isinstance(m, AIMessage) and any(tc["id"] not in answered for tc in m.tool_calls):
            ids = {tc["id"] for tc in m.tool_calls}
            orphans.append(m)
            orphans.extend(t for t in messages if isinstance(t, ToolMessage) and t.tool_call_id in ids)
    return orphans


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
    *,
    memory: MemoryService | None = None,
    conversations: ConversationStore | None = None,
    runtime_context: Callable[[], Awaitable[dict[str, str]]] | None = None,
):
    model_with_tools = llm.bind_tools(tools)
    # Nome e tag: é assim que se acha o prompt do summary no LangSmith (AC-04) e é a tag
    # que o runner usa para não streamar os tokens do resumo para o front.
    summarizer = llm.with_config(run_name="summarize_conversation", tags=[SUMMARIZER_TAG])

    async def compact(state: AgentState, config: RunnableConfig) -> dict:
        thread_id = _thread_id(config)
        orphans = orphan_tool_calls(state["messages"])
        orphan_ids = {m.id for m in orphans}
        removed = [RemoveMessage(id=m.id) for m in orphans if m.id]
        messages = [m for m in state["messages"] if m.id not in orphan_ids]
        stored = await summary_store.get(thread_id)
        previous = stored.summary if stored else ""

        to_compact, _ = policy.split(messages)
        if not to_compact:
            # Checkpoint pode ter expirado (TTL) e o summary continuar no banco: recarrega.
            update: dict = {"summary": previous} if previous != state.get("summary", "") else {}
            return {**update, "messages": removed} if removed else update

        prompt = SUMMARIZE_PROMPT.format(
            previous_summary=previous or "(nenhum)",
            transcript=_transcript(to_compact),
        )
        result = await summarizer.ainvoke([HumanMessage(content=prompt)])
        summary = result.content if isinstance(result.content, str) else message_text(result)
        await summary_store.upsert(thread_id, summary)
        if conversations:
            await conversations.record_usage(thread_id, "summary", result.usage_metadata)
        return {
            "summary": summary,
            "messages": [*removed, *(RemoveMessage(id=m.id) for m in to_compact if m.id)],
        }

    async def recall(state: AgentState) -> dict:
        return {"memories": await memory.recall(message_text(state["messages"][-1]))}

    async def model(state: AgentState) -> dict:
        runtime = await runtime_context() if runtime_context else None
        system = SystemMessage(content=build_system_prompt(state.get("summary"), state.get("memories"), runtime))
        response: AIMessage = await model_with_tools.ainvoke([system, *state["messages"]])
        return {"messages": [response]}

    graph = StateGraph(AgentState)
    graph.add_node("compact", compact)
    graph.add_node("model", model)
    graph.add_node("tools", ToolNode(tools))
    graph.add_edge(START, "compact")
    if memory:
        graph.add_node("recall", recall)
        graph.add_edge("compact", "recall")
        graph.add_edge("recall", "model")
    else:
        graph.add_edge("compact", "model")
    graph.add_conditional_edges("model", tools_condition, {"tools": "tools", END: END})
    graph.add_edge("tools", "model")
    return graph.compile(checkpointer=checkpointer, name=GRAPH_NAME)
