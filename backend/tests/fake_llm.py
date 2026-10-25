"""LLM falsa e determinística para os testes rodarem sem OPENAI_API_KEY.

Regras:
- prompt de compactação (começa com "Você compacta") -> devolve um resumo marcado;
- última mensagem humana fala de clima e ainda não houve tool -> pede `get_weather`;
- última mensagem é ToolMessage -> responde com a temperatura;
- senão -> ecoa.

Grava o último system prompt visto (`last_system_prompt`) para os testes checarem a injeção do summary.
"""

from __future__ import annotations

import json
from typing import Any, Iterator, Sequence

from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from langchain_core.tools import BaseTool
from pydantic import Field

SUMMARY_MARK = "[RESUMO FAKE]"


class FakeChatModel(BaseChatModel):
    calls: list[list[BaseMessage]] = Field(default_factory=list)
    last_system_prompt: str | None = None

    @property
    def _llm_type(self) -> str:
        return "fake-prax"

    def bind_tools(self, tools: Sequence[BaseTool | dict[str, Any]], **kwargs: Any):  # type: ignore[override]
        return self  # as tools são fixas nesta fake

    def _decide(self, messages: list[BaseMessage]) -> AIMessage:
        self.calls.append(list(messages))
        for m in messages:
            if isinstance(m, SystemMessage):
                self.last_system_prompt = str(m.content)
        last = messages[-1]
        if isinstance(last, HumanMessage) and str(last.content).startswith("Você compacta"):
            return AIMessage(content=f"{SUMMARY_MARK} {str(last.content)[-120:]}")
        if isinstance(last, ToolMessage):
            data = json.loads(last.content) if isinstance(last.content, str) else {}
            return AIMessage(content=f"Em {data.get('city')} faz {data.get('temp_c')}°C, {data.get('condition')}.")
        if isinstance(last, HumanMessage) and "clima" in str(last.content).lower():
            return AIMessage(
                content="",
                tool_calls=[{"name": "get_weather", "args": {"city": "São Paulo"}, "id": "call_1", "type": "tool_call"}],
            )
        return AIMessage(content=f"eco: {last.content}")

    def _generate(self, messages: list[BaseMessage], stop: list[str] | None = None,
                  run_manager: CallbackManagerForLLMRun | None = None, **kwargs: Any) -> ChatResult:
        return ChatResult(generations=[ChatGeneration(message=self._decide(messages))])

    def _stream(self, messages: list[BaseMessage], stop: list[str] | None = None,
                run_manager: CallbackManagerForLLMRun | None = None, **kwargs: Any) -> Iterator[ChatGenerationChunk]:
        msg = self._decide(messages)
        if msg.tool_calls:
            yield ChatGenerationChunk(message=AIMessageChunk(content="", tool_calls=msg.tool_calls))
            return
        words = str(msg.content).split(" ")
        for i, w in enumerate(words):
            yield ChatGenerationChunk(message=AIMessageChunk(content=(w if i == 0 else " " + w)))
