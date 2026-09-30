"""App completo (Redis real, SQLite real, SSE real) com a LLM falsa — para testar front e fumaça sem OpenAI.

    OPENAI_API_KEY=fake uv run uvicorn tests.e2e_app:app --port 8000
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.boot import boot
from app.main import create_app
from tests.fake_llm import FakeChatModel


@asynccontextmanager
async def fake_lifespan(app: FastAPI):
    async with boot(llm=FakeChatModel()) as resources:
        app.state.resources = resources
        yield


app = create_app()
app.router.lifespan_context = fake_lifespan
