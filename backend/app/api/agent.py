"""Rotas do agente (P1 · AC-01).

Este módulo NÃO importa LangGraph. Recebe o runner por dependência, chama, e serializa o que vier.
"""

from __future__ import annotations

import json
import uuid
from typing import Any, AsyncIterator, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.agent.runner import AgentRunner
from app.memory.conversation_store import ConversationStore

router = APIRouter(prefix="/agent", tags=["agent"])


class ExecuteRequest(BaseModel):
    message: str = Field(min_length=1)
    # O cliente manda só a mensagem atual + o id da thread. Nunca o histórico (D3 · AC-02).
    thread_id: str | None = None


class FeedbackRequest(BaseModel):
    run_id: str
    value: Literal["up", "down"] | None


def get_runner(request: Request) -> AgentRunner:
    return request.app.state.resources.runner


def get_conversations(request: Request) -> ConversationStore:
    return request.app.state.resources.conversations


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
        # Os 3 headers do gabarito do P1: resposta não cacheável, conexão viva enquanto a tool roda, proxy sem buffer.
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "X-Thread-Id": thread_id,
        },
    )


@router.get("/threads")
async def list_threads(conversations: ConversationStore = Depends(get_conversations)) -> dict[str, Any]:
    return {
        "threads": [
            {"thread_id": c.thread_id, "title": c.title, "last_used_at": c.last_used_at}
            for c in await conversations.list_recent()
        ]
    }


@router.get("/threads/{thread_id}")
async def thread_snapshot(thread_id: str, runner: AgentRunner = Depends(get_runner)) -> dict[str, Any]:
    snap = await runner.snapshot(thread_id)
    return {
        "thread_id": snap.thread_id,
        "checkpoint_alive": snap.checkpoint_alive,
        "summary": snap.summary,
        "messages": snap.messages,
        "transcript": snap.transcript,
    }


@router.delete("/threads/{thread_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_thread(thread_id: str, conversations: ConversationStore = Depends(get_conversations)) -> None:
    if not await conversations.soft_delete(thread_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "conversa não encontrada")


@router.post("/threads/{thread_id}/feedback", status_code=status.HTTP_204_NO_CONTENT)
async def set_feedback(
    thread_id: str, body: FeedbackRequest, conversations: ConversationStore = Depends(get_conversations)
) -> None:
    if not await conversations.set_feedback(thread_id, body.run_id, body.value):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "resposta não encontrada")


@router.get("/metrics")
async def metrics(conversations: ConversationStore = Depends(get_conversations)) -> dict[str, Any]:
    return await conversations.metrics()
