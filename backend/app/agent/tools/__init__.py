"""Registro de tools por factory (padrão da Live 04).

Todo módulo desta pasta que expõe `as_tool()` entra no agente automaticamente.
Para adicionar uma tool: cria `agent/tools/<nome>.py` com `as_tool()`; nada mais muda.
"""

from __future__ import annotations

import importlib
import pkgutil

from langchain_core.tools import BaseTool


def load_tools() -> list[BaseTool]:
    tools: list[BaseTool] = []
    for mod_info in pkgutil.iter_modules(__path__):
        module = importlib.import_module(f"{__name__}.{mod_info.name}")
        factory = getattr(module, "as_tool", None)
        if callable(factory):
            tools.append(factory())
    return tools
