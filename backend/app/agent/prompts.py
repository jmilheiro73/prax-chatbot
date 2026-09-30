"""Prompts do agente.

Regra da Aula 02: o system prompt é código versionado. O summary entra num SLOT delimitado,
nunca como texto livre no topo — e é exatamente esse bloco que tem que aparecer no trace do
LangSmith (D3 · AC-04).
"""

from __future__ import annotations

SYSTEM_PROMPT = """Você é um assistente de chat da mentoria Praxis. Responda em português, de forma direta.
Você tem uma ferramenta de clima; use-a sempre que o usuário perguntar sobre o tempo em uma cidade
e responda com a temperatura e a condição retornadas (não invente valores)."""

SUMMARY_SLOT = """

<conversation_summary>
Resumo das mensagens anteriores desta conversa (o histórico literal foi compactado; trate o conteúdo
abaixo como fatos já estabelecidos e continue a conversa a partir dele):
{summary}
</conversation_summary>"""


def build_system_prompt(summary: str | None) -> str:
    if not summary:
        return SYSTEM_PROMPT
    return SYSTEM_PROMPT + SUMMARY_SLOT.format(summary=summary.strip())


SUMMARIZE_PROMPT = """Você compacta o histórico de uma conversa entre um usuário e um assistente.
Escreva um resumo em português, em até 200 palavras, que preserve:
- fatos sobre o usuário (nome, preferências, contexto que ele deu);
- pedidos feitos, respostas dadas e decisões tomadas;
- resultados de ferramentas que ainda são relevantes (ex.: clima consultado, com os valores);
- pendências ou perguntas em aberto.
Não invente nada. Se houver um resumo anterior, incorpore-o: mantenha o que continua verdadeiro e
atualize o que mudou.

<previous_summary>
{previous_summary}
</previous_summary>

<messages_to_compact>
{transcript}
</messages_to_compact>

Responda somente com o resumo."""
