"""FastAPI: routers + lifespan. Nada de lógica de agente aqui."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.agent import router as agent_router
from app.boot import lifespan
from app.settings import load_settings


def create_app() -> FastAPI:
    settings = load_settings()
    app = FastAPI(title="praxis-chatbot", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Thread-Id"],
    )
    app.include_router(agent_router)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
