"""Chunking (Aula 14): por estrutura quando dá, recursivo por tokens no resto."""

from __future__ import annotations

from app.agent.tokens import count_text_tokens
from app.rag.chunking import chunk_document


def test_markdown_vira_secoes_com_o_caminho_do_titulo():
    chunks = chunk_document("# Guia\nintro\n\n## Instalação\npasso um\n\n## Uso\nchame a API\n")
    assert [c.section for c in chunks] == ["Guia", "Guia > Instalação", "Guia > Uso"]
    assert chunks[1].content == "passo um"
    assert [c.order for c in chunks] == [0, 1, 2]


def test_titulo_dentro_de_bloco_de_codigo_nao_abre_secao():
    chunks = chunk_document("# Guia\n```\n# comentário de shell\n```\n")
    assert [c.section for c in chunks] == ["Guia"]
    assert "comentário de shell" in chunks[0].content


def test_secao_grande_respeita_o_limite_de_tokens():
    text = "\n\n".join(f"Parágrafo {i} com algumas palavras para ocupar espaço no chunk." for i in range(200))
    chunks = chunk_document(text, max_tokens=50)
    assert len(chunks) > 1
    assert all(count_text_tokens(c.content) <= 50 for c in chunks)
    assert "Parágrafo 199" in chunks[-1].content


def test_texto_sem_separador_ainda_e_cortado():
    chunks = chunk_document("x" * 5000, max_tokens=20)
    assert len(chunks) > 1
    assert all(count_text_tokens(c.content) <= 25 for c in chunks)


def test_hash_nao_muda_quando_o_trecho_nao_muda():
    a = chunk_document("# A\num\n\n# B\ndois\n")
    b = chunk_document("# A\num\n\n# B\ndois alterado\n")
    assert a[0].hash == b[0].hash
    assert a[1].hash != b[1].hash


def test_documento_vazio_nao_gera_chunk():
    assert chunk_document("   \n\n") == []
