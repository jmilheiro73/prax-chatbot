"""LLM falsa e determinística para os testes rodarem sem OPENAI_API_KEY.

Regras:
- prompt de compactação (começa com "Você compacta") -> devolve um resumo marcado;
- system prompt de especialista -> busca nos documentos e depois encerra;
- última mensagem é ToolMessage -> responde com base no resultado da tool;
- última mensagem humana fala de clima -> pede `get_weather`;
- fala de "pesquise a fundo" -> pede `delegate_research`; fala de "documento" -> pede `search_documents`;
- senão -> ecoa.

`with_structured_output` devolve objetos prontos por schema, como a API faria.
Grava o último system prompt visto (`last_system_prompt`) para os testes checarem a injeção do summary.
"""

from __future__ import annotations

import json
import re
import uuid
from typing import Any, Iterator, Sequence

from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from langchain_core.runnables import RunnableLambda
from langchain_core.tools import BaseTool
from pydantic import Field

from app.agent.schemas import ConversationTitle, ExtractedMemory, MemoryExtraction, TaskResult

SUMMARY_MARK = "[RESUMO FAKE]"
USAGE = {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15}


def _call(name: str, **args: Any) -> dict[str, Any]:
    return {"name": name, "args": args, "id": f"call_{uuid.uuid4().hex[:8]}", "type": "tool_call"}


def _text_of(value: Any) -> str:
    if isinstance(value, str):
        return value
    return "\n".join(str(m.content) for m in value)


def _extract_memories(prompt: str) -> MemoryExtraction:
    found = re.search(r"<user_message>(.*?)</user_message>", prompt, re.S)
    message = found.group(1) if found else ""
    memories = []
    if name := re.search(r"meu nome é (\w+)", message, re.I):
        memories.append(ExtractedMemory(type="profile", content=f"O nome do usuário é {name.group(1)}."))
    if city := re.search(r"moro em (\w+)", message, re.I):
        memories.append(ExtractedMemory(type="fact", content=f"O usuário mora em {city.group(1)}."))
    if secret := re.search(r"minha senha é (\w+)", message, re.I):
        memories.append(ExtractedMemory(type="fact", content=f"A senha do usuário é {secret.group(1)}."))
    return MemoryExtraction(reasoning="regra da fake", memories=memories)


class FakeChatModel(BaseChatModel):
    calls: list[list[BaseMessage]] = Field(default_factory=list)
    structured_prompts: list[str] = Field(default_factory=list)
    last_system_prompt: str | None = None

    @property
    def _llm_type(self) -> str:
        return "fake-prax"

    def bind_tools(self, tools: Sequence[BaseTool | dict[str, Any]], **kwargs: Any):  # type: ignore[override]
        return self  # as tools são fixas nesta fake

    def with_structured_output(self, schema: Any, *, include_raw: bool = False, **kwargs: Any):  # type: ignore[override]
        def respond(value: Any) -> Any:
            prompt = _text_of(value)
            self.structured_prompts.append(prompt)
            if schema is ConversationTitle:
                parsed: Any = ConversationTitle(title="Título da fake")
            elif schema is MemoryExtraction:
                parsed = _extract_memories(prompt)
            elif schema is TaskResult:
                parsed = TaskResult(reasoning="regra da fake", status="done", summary="Resumo do especialista.", sources=["doc"])
            elif schema.__name__ == "JudgeVerdict":
                parsed = schema(reasoning="regra da fake", grounded="yes")
            else:
                parsed = schema()
            if not include_raw:
                return parsed
            return {
                "raw": AIMessage(content=parsed.model_dump_json(), usage_metadata=USAGE),
                "parsed": parsed,
                "parsing_error": None,
            }

        return RunnableLambda(respond)

    def _after_tool(self, last: ToolMessage) -> AIMessage:
        if last.name == "search_documents":
            hits = json.loads(last.content)
            return AIMessage(content=f"Segundo os documentos: {hits[0]['text']}" if hits else "Não encontrei nos documentos.")
        if last.name == "delegate_research":
            return AIMessage(content=f"Pesquisa: {json.loads(last.content)['summary']}")
        data = json.loads(last.content)
        return AIMessage(content=f"Em {data.get('city')} faz {data.get('temp_c')}°C, {data.get('condition')}.")

    def _decide(self, messages: list[BaseMessage]) -> AIMessage:
        self.calls.append(list(messages))
        for m in messages:
            if isinstance(m, SystemMessage):
                self.last_system_prompt = str(m.content)
        last = messages[-1]
        specialist = "especialista em pesquisa" in (self.last_system_prompt or "") and isinstance(messages[0], SystemMessage)
        if isinstance(last, HumanMessage) and str(last.content).startswith("Você compacta"):
            return AIMessage(content=f"{SUMMARY_MARK} {str(last.content)[-120:]}", usage_metadata=USAGE)
        if specialist:
            if isinstance(last, ToolMessage):
                return AIMessage(content="Pesquisa concluída.")
            return AIMessage(content="", tool_calls=[_call("search_documents", query=str(last.content))])
        if isinstance(last, ToolMessage):
            return self._after_tool(last)
        text = str(last.content).lower() if isinstance(last, HumanMessage) else ""
        if "clima" in text:
            return AIMessage(content="", tool_calls=[_call("get_weather", city="São Paulo")])
        if "pesquise a fundo" in text:
            return AIMessage(content="", tool_calls=[_call("delegate_research", task=str(last.content))])
        if "documento" in text or "férias" in text or "refeições" in text or "suporte" in text:
            return AIMessage(content="", tool_calls=[_call("search_documents", query=str(last.content))])
        return AIMessage(content=f"eco: {last.content}")

    def _generate(self, messages: list[BaseMessage], stop: list[str] | None = None,
                  run_manager: CallbackManagerForLLMRun | None = None, **kwargs: Any) -> ChatResult:
        return ChatResult(generations=[ChatGeneration(message=self._decide(messages))])

    def _stream(self, messages: list[BaseMessage], stop: list[str] | None = None,
                run_manager: CallbackManagerForLLMRun | None = None, **kwargs: Any) -> Iterator[ChatGenerationChunk]:
        msg = self._decide(messages)
        if msg.tool_calls:
            yield ChatGenerationChunk(message=AIMessageChunk(content="", tool_calls=msg.tool_calls, usage_metadata=USAGE))
            return
        words = str(msg.content).split(" ")
        for i, w in enumerate(words):
            yield ChatGenerationChunk(message=AIMessageChunk(content=(w if i == 0 else " " + w)))
        yield ChatGenerationChunk(message=AIMessageChunk(content="", usage_metadata=USAGE))
