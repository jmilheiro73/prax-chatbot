"""Registro de tools por factory (padrão da Live 04).

Todo módulo desta pasta que expõe `as_tool()` entra no agente automaticamente. Quem precisa de um recurso do
boot (a base de conhecimento, por exemplo) expõe `as_tools(ctx)` e recebe o `ToolContext`.
Para adicionar uma tool: cria `agent/tools/<nome>.py` com a factory; nada mais muda.
"""

from __future__ import annotations

import importlib
import pkgutil
from dataclasses import dataclass
from typing import TYPE_CHECKING

from langchain_core.tools import BaseTool

if TYPE_CHECKING:
    from app.rag.service import KnowledgeService


@dataclass(frozen=True)
class ToolContext:
    knowledge: "KnowledgeService | None" = None


def load_tools(ctx: ToolContext | None = None) -> list[BaseTool]:
    tools: list[BaseTool] = []
    for mod_info in pkgutil.iter_modules(__path__):
        module = importlib.import_module(f"{__name__}.{mod_info.name}")
        factory = getattr(module, "as_tool", None)
        if callable(factory):
            tools.append(factory())
        many = getattr(module, "as_tools", None)
        if callable(many):
            tools.extend(many(ctx))
    return tools
