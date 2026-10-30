"""Ingestão e busca (Aulas 14 a 16). Precisa de Redis: o índice HNSW é real; os embeddings são falsos."""

from __future__ import annotations

import pytest

DOC = """# Manual

## Férias
O colaborador tem trinta dias de férias por ano.

## Reembolso
Despesas de viagem são reembolsadas em até dez dias.
"""


async def test_ingestao_fica_pronta_e_a_busca_acha_o_trecho(knowledge):
    doc, queued = await knowledge.submit("manual.md", DOC)
    assert queued and doc.status == "queued"
    await knowledge.wait_until_idle()

    ready = (await knowledge.list_documents())[0]
    assert ready.status == "ready" and ready.chunk_count == 2

    hits = await knowledge.search("quantos dias de férias o colaborador tem?")
    assert hits[0]["section"] == "Manual > Férias"
    assert hits[0]["document"] == "manual.md"
    assert 0 < hits[0]["score"] <= 1


async def test_mesmo_conteudo_nao_reprocessa(knowledge, fake_embeddings):
    await knowledge.submit("manual.md", DOC)
    await knowledge.wait_until_idle()
    embedded = len(fake_embeddings.texts)

    _, queued = await knowledge.submit("manual.md", DOC)
    await knowledge.wait_until_idle()
    assert not queued
    assert len(fake_embeddings.texts) == embedded


async def test_reenvio_so_reembeda_o_que_mudou(knowledge, fake_embeddings):
    await knowledge.submit("manual.md", DOC)
    await knowledge.wait_until_idle()
    fake_embeddings.texts.clear()

    await knowledge.submit("manual.md", DOC.replace("dez dias", "vinte dias"))
    await knowledge.wait_until_idle()

    assert len(fake_embeddings.texts) == 1 and "vinte dias" in fake_embeddings.texts[0]
    doc = (await knowledge.list_documents())[0]
    assert doc.version == 2 and doc.reused_chunks == 1 and doc.chunk_count == 2
    hits = await knowledge.search("reembolso de despesas de viagem")
    assert "vinte dias" in hits[0]["text"]
    assert all("dez dias" not in h["text"] for h in hits)


async def test_apagar_tira_do_indice_e_do_banco(knowledge, chunk_index):
    doc, _ = await knowledge.submit("manual.md", DOC)
    await knowledge.wait_until_idle()
    assert await knowledge.delete(doc.id)
    assert await knowledge.search("férias") == []
    assert await chunk_index.count() == 0
    assert not await knowledge.delete(doc.id)


async def test_busca_filtra_por_documento(knowledge):
    a, _ = await knowledge.submit("a.md", "# A\nfalamos de férias aqui\n")
    b, _ = await knowledge.submit("b.md", "# B\nfalamos de férias ali\n")
    await knowledge.wait_until_idle()
    assert [h["document"] for h in await knowledge.search("férias", document=b.id)] == ["b.md"]
    assert [h["document"] for h in await knowledge.search("férias", document="a.md")] == ["a.md"]
    assert a.id != b.id


async def test_filtro_que_nao_casa_e_erro_e_nao_lista_vazia(knowledge):
    """A eval real pegou isto: com lista vazia, o modelo afirmava que o documento não tinha a informação."""
    from app.agent.tools import ToolContext
    from app.agent.tools.knowledge import as_tools
    from app.rag.service import DocumentNotFound

    await knowledge.submit("a.md", "# A\nfalamos de férias aqui\n")
    await knowledge.wait_until_idle()
    with pytest.raises(DocumentNotFound):
        await knowledge.search("férias", document="nao-existe.md")

    search = next(t for t in as_tools(ToolContext(knowledge=knowledge)) if t.name == "search_documents")
    assert "não encontrado" in await search.ainvoke({"query": "férias", "document": "nao-existe.md"})
    assert "a.md" in await search.ainvoke({"query": "férias", "document": "a.md"})


async def test_documento_sem_texto_vira_erro(knowledge):
    await knowledge.submit("vazio.md", "   ")
    await knowledge.wait_until_idle()
    doc = (await knowledge.list_documents())[0]
    assert doc.status == "error" and doc.error


async def test_indice_vazio_e_reconstruido_sem_novo_embedding(db, knowledge, chunk_index, fake_embeddings):
    """O Redis aqui é efêmero: se ele reiniciar, os vetores voltam do SQLite."""
    from app.rag.service import KnowledgeService
    from app.rag.store import KnowledgeStore

    await knowledge.submit("manual.md", DOC)
    await knowledge.wait_until_idle()
    await chunk_index.delete([f"{r.id}" for r in await KnowledgeStore(db, "tester").all_chunks()])
    assert await chunk_index.count() == 0
    fake_embeddings.texts.clear()

    again = KnowledgeService(KnowledgeStore(db, "tester"), chunk_index, fake_embeddings, "fake")
    await again.start()
    await again.stop()
    assert await chunk_index.count() == 2
    assert fake_embeddings.texts == []


async def test_read_around_traz_os_vizinhos(knowledge):
    await knowledge.submit("manual.md", DOC)
    await knowledge.wait_until_idle()
    first = (await knowledge.search("férias"))[0]
    around = await knowledge.read_around(first["chunk_id"])
    assert {a["section"] for a in around} == {"Manual > Férias", "Manual > Reembolso"}
    assert await knowledge.read_around("nao-existe") == []


async def test_status_line_para_o_runtime_context(knowledge):
    assert await knowledge.status_line() == "nenhum"
    await knowledge.submit("manual.md", DOC)
    await knowledge.wait_until_idle()
    assert await knowledge.status_line() == "1 pronto(s): manual.md"


@pytest.mark.parametrize("bad", [""])
async def test_api_valida_o_corpo(bad):
    from app.api.knowledge import DocumentRequest

    with pytest.raises(ValueError):
        DocumentRequest(name="x.md", content=bad)
