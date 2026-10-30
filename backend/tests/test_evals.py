"""A mecânica das evals, com a LLM falsa. Quem mede qualidade de verdade é `python -m evals.run` com o modelo real."""

from __future__ import annotations

from evals.evaluators import EvalRun, answer_contains, memory_recall, memory_safety, recall_at_k, tool_choice
from evals.export_feedback import merge_items
from evals.run import load_dataset, load_settings_for_fake, regressions, run_evals
from tests.fake_embeddings import FakeEmbeddings
from tests.fake_llm import FakeChatModel


def test_evaluators_deterministicos():
    run = EvalRun(answer="Faz 22°C", tools_called=["get_weather"], retrieved_sections=["A", "B"])
    assert tool_choice(run, {"tools": ["get_weather"]}) == 1
    assert tool_choice(run, {"no_tools": True}) == 0
    assert tool_choice(run, {"tools_any": ["x", "get_weather"]}) == 1
    assert tool_choice(run, {}) is None
    assert answer_contains(run, {"contains": ["22"]}) == 1
    assert answer_contains(run, {"contains": ["30"]}) == 0
    assert recall_at_k(run, {"sections": ["A", "C"]}) == 0.5
    assert recall_at_k(run, {}) is None

    run = EvalRun(answer="", recalled_memories=["Mora em Niterói"], all_memories=["Mora em Niterói"])
    assert memory_recall(run, {"recall_contains": ["niterói"]}) == 1
    assert memory_recall(run, {"recall_excludes": ["niterói"]}) == 0
    assert memory_safety(run, {"memory_excludes": ["caixa alta"]}) == 1


def test_regressions_so_acusa_o_que_piorou():
    assert regressions({"a": 0.5, "b": 1.0, "c": 0.9}, {"a": 0.7, "b": 1.0}) == ["a"]


def test_export_feedback_nao_repete_pergunta():
    existing = [{"id": "feedback-1", "input": "já tenho"}]
    rated = [{"question": "já tenho", "answer": "x"}, {"question": "nova", "answer": "ruim"}, {"question": "", "answer": "y"}]
    merged = merge_items(existing, rated)
    assert [m["input"] for m in merged] == ["já tenho", "nova"]
    assert merged[1]["bad_answer"] == "ruim" and merged[1]["expect"] == {}


async def test_dataset_inteiro_roda_pelo_boot_real():
    result = await run_evals(load_settings_for_fake(), FakeChatModel(), FakeEmbeddings(), judge=FakeChatModel())
    assert {i["id"] for i in result["items"]} == {i["id"] for i in load_dataset()}
    assert result["summary"]["tool_choice"] == 1.0
    assert result["summary"]["recall_at_k"] == 1.0
    assert result["summary"]["memory_recall"] == 1.0
    assert result["summary"]["memory_safety"] == 1.0
    assert result["summary"]["groundedness"] == 1.0
    assert result["usage"]["chat"]["calls"] > 0
