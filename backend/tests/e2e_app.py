"""App completo (Redis real, SQLite real, SSE real) com a LLM falsa — para testar front e fumaça sem OpenAI.

    OPENAI_API_KEY=fake uv run uvicorn tests.e2e_app:app --port 8000
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.boot import boot
from app.main import create_app
from app.settings import load_settings
from tests.fake_embeddings import FakeEmbeddings
from tests.fake_llm import FakeChatModel


@asynccontextmanager
async def fake_lifespan(app: FastAPI):
    # Banco e índices próprios: o que se testa aqui não aparece nas suas conversas reais.
    settings = load_settings().model_copy(
        update={
            "embedding_dims": FakeEmbeddings.DIMS,
            "embedding_model": "fake",
            "app_db_path": "data/e2e.sqlite",
            "summary_db_path": "data/e2e-summaries.sqlite",
            "index_prefix": "prax-e2e",
        }
    )
    async with boot(settings, llm=FakeChatModel(), embeddings=FakeEmbeddings()) as resources:
        app.state.resources = resources
        yield


app = create_app()
app.router.lifespan_context = fake_lifespan
