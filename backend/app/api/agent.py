"""Rotas do agente (P1 · AC-01).

Este módulo NÃO importa LangGraph. Recebe o runner por dependência, chama, e serializa o que vier.
"""

from __future__ import annotations

import json
import uuid
from typing import Any, AsyncIterator

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.agent.runner import AgentRunner

router = APIRouter(prefix="/agent", tags=["agent"])


class ExecuteRequest(BaseModel):
    message: str = Field(min_length=1)
    # O cliente manda só a mensagem atual + o id da thread. Nunca o histórico (D3 · AC-02).
    thread_id: str | None = None


def get_runner(request: Request) -> AgentRunner:
    return request.app.state.resources.runner


def _json_default(obj: Any) -> Any:
    """Serializa o que o LangChain põe dentro do StreamEvent (mensagens, chunks, etc.)."""
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    if isinstance(obj, (set, frozenset)):
        return list(obj)
    return str(obj)


def encode_sse(event: dict[str, Any]) -> str:
    """P1 · AC-05: `event:` = o `event` do StreamEvent; `data:` = o StreamEvent inteiro."""
    payload = json.dumps(event, default=_json_default, ensure_ascii=False)
    return f"event: {event['event']}\ndata: {payload}\n\n"


async def _sse(events: AsyncIterator[dict[str, Any]]) -> AsyncIterator[str]:
    async for event in events:
        yield encode_sse(event)


@router.post("/execute")
async def execute(body: ExecuteRequest, runner: AgentRunner = Depends(get_runner)) -> StreamingResponse:
    thread_id = body.thread_id or str(uuid.uuid4())
    return StreamingResponse(
        _sse(runner.stream(body.message, thread_id)),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "X-Thread-Id": thread_id,
        },
    )


@router.get("/threads/{thread_id}")
async def thread_snapshot(thread_id: str, runner: AgentRunner = Depends(get_runner)) -> dict[str, Any]:
    snap = await runner.snapshot(thread_id)
    return {
        "thread_id": snap.thread_id,
        "checkpoint_alive": snap.checkpoint_alive,
        "summary": snap.summary,
        "messages": snap.messages,
    }
