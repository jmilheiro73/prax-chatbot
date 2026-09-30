"""Tool de clima — stub de propósito (P1 · AC-03).

Sem HTTP, `sleep ~2s` para o front ter tempo de pintar o estado "tool rodando",
e retorno fixo para o teste de fumaça ser determinístico (AC-08: frase com 22°C).
"""

from __future__ import annotations

import asyncio

from langchain_core.tools import BaseTool, tool


@tool
async def get_weather(city: str) -> dict:
    """Consulta o clima atual de uma cidade. Use quando o usuário perguntar sobre tempo/clima."""
    await asyncio.sleep(2)
    return {"city": city, "temp_c": 22, "condition": "parcialmente nublado"}


def as_tool() -> BaseTool:
    return get_weather
