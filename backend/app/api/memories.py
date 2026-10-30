"""Memória editável (Live 05): não é porque a LLM gerou que o usuário não pode corrigir ou apagar."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from app.memory.memory_store import Memory
from app.memory.service import MemoryService

router = APIRouter(prefix="/memories", tags=["memories"])


class MemoryCreate(BaseModel):
    type: Literal["fact", "profile"] = "fact"
    content: str = Field(min_length=1, max_length=500)


class MemoryUpdate(BaseModel):
    content: str = Field(min_length=1, max_length=500)


def get_memory(request: Request) -> MemoryService:
    service = request.app.state.resources.memory
    if service is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "memória desligada (MEMORY_ENABLED=false)")
    return service


def _public(memory: Memory) -> dict[str, Any]:
    return {
        "id": memory.id,
        "type": memory.type,
        "content": memory.content,
        "source_thread_id": memory.source_thread_id,
        "updated_at": memory.updated_at,
    }


@router.get("")
async def list_memories(service: MemoryService = Depends(get_memory)) -> dict[str, Any]:
    return {"memories": [_public(m) for m in await service.list_memories()]}


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_memory(body: MemoryCreate, service: MemoryService = Depends(get_memory)) -> dict[str, Any]:
    return _public(await service.create(body.type, body.content))


@router.patch("/{memory_id}")
async def update_memory(memory_id: str, body: MemoryUpdate, service: MemoryService = Depends(get_memory)) -> dict[str, Any]:
    memory = await service.update(memory_id, body.content)
    if memory is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "memória não encontrada")
    return _public(memory)


@router.delete("/{memory_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_memory(memory_id: str, service: MemoryService = Depends(get_memory)) -> None:
    if not await service.delete(memory_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "memória não encontrada")
