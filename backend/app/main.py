"""FastAPI: routers + lifespan. Nada de lógica de agente aqui."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.agent import router as agent_router
from app.api.knowledge import router as knowledge_router
from app.api.mcp import router as mcp_router
from app.api.memories import router as memories_router
from app.boot import lifespan
from app.settings import load_settings


def create_app() -> FastAPI:
    settings = load_settings()
    app = FastAPI(title="prax-chatbot", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Thread-Id"],
    )
    app.include_router(agent_router)
    app.include_router(knowledge_router)
    app.include_router(memories_router)
    app.include_router(mcp_router)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
