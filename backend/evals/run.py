"""Eval offline (Live 08): dataset -> agente -> runs -> evaluators -> métrica, comparada com a última run.

    uv run python -m evals.run --fake            # sem OpenAI: confere a mecânica, de graça
    uv run python -m evals.run                   # modelo real: gasta tokens
    uv run python -m evals.run --judge           # + LLM-as-a-judge de groundedness (gasta mais)
    uv run python -m evals.run --scenario rag    # só um cenário do dataset

O agente roda pelo mesmo `boot()` da API, com banco temporário e índices próprios: é o sistema de verdade, não um mock.
Precisa do Redis no ar. Sai com código 1 se alguma métrica piorar em relação à última run do mesmo modo.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from langchain_core.embeddings import Embeddings
from langchain_core.language_models import BaseChatModel

from app.boot import boot
from app.settings import Settings, load_settings
from evals.evaluators import DETERMINISTIC, EvalRun, groundedness

HERE = Path(__file__).parent
DATASET = HERE / "datasets" / "chat.jsonl"
CORPUS = HERE / "corpus"
RESULTS = HERE / "results"


def load_dataset(path: Path = DATASET) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


async def _run_item(resources: Any, run_prefix: str, item: dict[str, Any], judge: BaseChatModel | None) -> dict[str, Any]:
    run = EvalRun(answer="")
    thread_id = f"{run_prefix}-{item.get('thread', item['id'])}"
    async for event in resources.runner.stream(item["input"], thread_id):
        if event["event"] == "on_tool_end":
            run.tools_called.append(event["name"])
            run.tool_results.append(str(getattr(event["data"].get("output"), "content", "")))
        elif event["event"] == "on_chat_model_end":
            run.answer = str(event["data"]["output"].content) or run.answer
    await resources.background.drain()

    expect = item["expect"]
    if "sections" in expect:
        run.retrieved_sections = [h["section"] for h in await resources.knowledge.search(item["input"])]
    if resources.memory:
        run.recalled_memories = await resources.memory.recall(item["input"])
        run.all_memories = [m.content for m in await resources.memory.list_memories()]

    scores = {name: evaluator(run, expect) for name, evaluator in DETERMINISTIC.items()}
    if judge and expect.get("grounded"):
        scores["groundedness"] = await groundedness(judge, item["input"], run)
    return {
        "id": item["id"],
        "scenario": item["scenario"],
        "scores": {k: v for k, v in scores.items() if v is not None},
        "answer": run.answer,
        "tools": run.tools_called,
        "recalled_memories": run.recalled_memories,
    }


def _summarize(items: list[dict[str, Any]]) -> dict[str, float]:
    collected: dict[str, list[float]] = {}
    for item in items:
        for name, value in item["scores"].items():
            collected.setdefault(name, []).append(value)
    return {name: round(sum(values) / len(values), 3) for name, values in sorted(collected.items())}


def _previous_run(mode: str, results_dir: Path) -> dict[str, Any] | None:
    runs = sorted(results_dir.glob(f"{mode}-*.json"))
    return json.loads(runs[-1].read_text(encoding="utf-8")) if runs else None


def regressions(current: dict[str, float], previous: dict[str, float]) -> list[str]:
    return [name for name, value in current.items() if name in previous and value < previous[name]]


async def run_evals(
    settings: Settings,
    llm: BaseChatModel | None = None,
    embeddings: Embeddings | None = None,
    judge: BaseChatModel | None = None,
    dataset: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Roda o dataset e devolve as métricas. Não escreve nada fora do diretório temporário."""
    run_prefix = f"eval-{uuid.uuid4().hex[:8]}"
    with tempfile.TemporaryDirectory() as tmp:
        settings = settings.model_copy(
            update={
                "app_db_path": f"{tmp}/prax.sqlite",
                "summary_db_path": f"{tmp}/summaries.sqlite",
                "index_prefix": f"prax-{run_prefix}",
                # Sem o limite de teste do D3 do `.env`. O TTL é curto para a run não deixar chaves no Redis por horas.
                "summary_token_limit": 4_000,
                "checkpoint_ttl_seconds": 120,
            }
        )
        async with boot(settings, llm=llm, embeddings=embeddings) as resources:
            try:
                for path in sorted(CORPUS.glob("*")):
                    await resources.knowledge.submit(path.name, path.read_text(encoding="utf-8"))
                await resources.knowledge.wait_until_idle()
                # Em ordem: a conversa "b" depende do que a "a" gravou.
                items = [await _run_item(resources, run_prefix, item, judge) for item in dataset or load_dataset()]
                usage = (await resources.conversations.metrics())["usage_by_purpose"]
            finally:
                await resources.background.drain()
                for index in resources.vector_indexes:
                    await index.drop()
    return {"summary": _summarize(items), "usage": usage, "items": items}


def _print_report(result: dict[str, Any], previous: dict[str, Any] | None) -> None:
    for item in result["items"]:
        failed = [name for name, value in item["scores"].items() if value < 1]
        mark = "FALHOU " + ", ".join(failed) if failed else "ok"
        print(f"  {item['scenario']:<10} {item['id']:<24} {mark}")
    print()
    before = previous["summary"] if previous else {}
    for name, value in result["summary"].items():
        delta = f" (antes {before[name]})" if name in before and before[name] != value else ""
        print(f"  {name:<18} {value:.3f}{delta}")
    tokens = sum(u["input_tokens"] + u["output_tokens"] for u in result["usage"].values())
    print(f"\n  tokens gastos: {tokens}")


async def _main() -> int:
    parser = argparse.ArgumentParser(description="Eval offline do Prax")
    parser.add_argument("--fake", action="store_true", help="usa a LLM e os embeddings falsos dos testes")
    parser.add_argument("--judge", action="store_true", help="liga o LLM-as-a-judge de groundedness")
    parser.add_argument("--scenario", action="append", help="roda só este cenário; pode repetir")
    args = parser.parse_args()
    dataset = [i for i in load_dataset() if not args.scenario or i["scenario"] in args.scenario]

    if args.fake:
        from tests.fake_embeddings import FakeEmbeddings
        from tests.fake_llm import FakeChatModel

        llm, embeddings = FakeChatModel(), FakeEmbeddings()
        settings = load_settings_for_fake()
        judge = llm if args.judge else None
    else:
        settings = load_settings()
        llm, embeddings, judge = None, None, None
        if args.judge:
            from langchain_openai import ChatOpenAI

            judge = ChatOpenAI(model=settings.openai_model, api_key=settings.openai_api_key)

    mode = "fake" if args.fake else "real"
    previous = _previous_run(mode, RESULTS)
    result = await run_evals(settings, llm, embeddings, judge, dataset)
    _print_report(result, previous)

    RESULTS.mkdir(exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    (RESULTS / f"{mode}-{stamp}.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    worse = regressions(result["summary"], previous["summary"]) if previous else []
    if worse:
        print(f"\n  regressão em: {', '.join(worse)}")
    return 1 if worse else 0


def load_settings_for_fake() -> Settings:
    from tests.fake_embeddings import FakeEmbeddings

    # Sem `.env`: a run falsa não pode depender de chave nenhuma.
    return Settings(
        _env_file=None, OPENAI_API_KEY="fake", EMBEDDING_DIMS=FakeEmbeddings.DIMS, EMBEDDING_MODEL="fake",
        MEMORY_MIN_SIMILARITY=0.15,
    )


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
