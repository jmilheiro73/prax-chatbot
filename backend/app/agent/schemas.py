"""Contratos de output estruturado (Aula 07): "um é pedido, o outro é obrigação".

- `Literal` nos domínios fechados: o modelo não inventa categoria.
- `reasoning` primeiro: a LLM é autorregressiva, e o campo de cima condiciona os de baixo.
- `Field(description=...)` vai para o schema, então é prompt também.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ConversationTitle(BaseModel):
    title: str = Field(description="Título de até 6 palavras, em português, sem aspas nem ponto final.")


class ExtractedMemory(BaseModel):
    type: Literal["fact", "profile"] = Field(
        description="`profile` só para nome, idioma e como o usuário quer as respostas: entra em toda conversa. "
        "`fact` para todo o resto, como onde mora, trabalho e gostos: entra só quando o assunto volta."
    )
    content: str = Field(description="Uma frase curta na terceira pessoa. Ex.: 'O usuário mora em Niterói.'")


class MemoryExtraction(BaseModel):
    reasoning: str = Field(description="Em uma frase: o que nesta troca muda como responder ao usuário no futuro?")
    memories: list[ExtractedMemory] = Field(description="Vazia na maioria das vezes.")


class TaskResult(BaseModel):
    """O contrato de volta do subagente (Aula 19): `done` + resumo, sem o contexto inteiro."""

    reasoning: str = Field(description="Em uma frase: a pesquisa respondeu à tarefa?")
    status: Literal["done", "blocked"] = Field(
        description="`done` se a tarefa foi respondida; `blocked` se faltou informação nos documentos."
    )
    summary: str = Field(description="A resposta para o orquestrador, só com o que ele precisa para seguir.")
    sources: list[str] = Field(description="Os documentos usados, no formato 'documento > seção'.")
