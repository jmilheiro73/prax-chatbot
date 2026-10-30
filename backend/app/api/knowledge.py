"""Rotas da base de conhecimento: 202 + worker (Aula 14). A rota só enfileira."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from app.rag.service import KnowledgeService

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


class DocumentRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=500_000)


def get_knowledge(request: Request) -> KnowledgeService:
    return request.app.state.resources.knowledge


@router.post("/documents", status_code=status.HTTP_202_ACCEPTED)
async def submit_document(body: DocumentRequest, knowledge: KnowledgeService = Depends(get_knowledge)) -> dict[str, Any]:
    document, queued = await knowledge.submit(body.name, body.content)
    return {"document": asdict(document), "queued": queued}


@router.get("/documents")
async def list_documents(knowledge: KnowledgeService = Depends(get_knowledge)) -> dict[str, Any]:
    return {"documents": [asdict(d) for d in await knowledge.list_documents()]}


@router.delete("/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(document_id: str, knowledge: KnowledgeService = Depends(get_knowledge)) -> None:
    if not await knowledge.delete(document_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "documento não encontrado")
