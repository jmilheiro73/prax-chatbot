# Mapa: o que cada aula virou neste projeto

Para cada tema do curso: se entrou no chatbot, onde está, e por que ficou de fora quando não coube.
Critério: entra o que resolve um problema real deste chat. O próprio curso pede isso ("escopo fechado não precisa de X").

## Entrou

| Aula | Tema | O que virou | Onde |
|---|---|---|---|
| 02 | `usage` em vez de `tiktoken` para custo | Tokens reais por resposta e por finalidade | `memory/conversation_store.py` (`llm_usage`), `GET /agent/metrics`, rodapé da resposta |
| 02 | Zombie request | Botão parar: cancela o stream e a chamada à OpenAI | `Composer.tsx`, `page.tsx` (`AbortController`) |
| 02 | `call_id` é sagrado | Tool call sem resultado sai do estado antes do próximo turno | `agent/graph.py` (`orphan_tool_calls`) |
| 06b | 3 headers SSE | `Connection: keep-alive` incluído | `api/agent.py` |
| 07 | Structured output (`Literal`, `reasoning` primeiro) | Título, extração de memória, resultado do subagente e juiz | `agent/schemas.py` |
| 08 | Extrações determinísticas antes da LLM | Filtro que evita chamar a LLM de memória à toa | `memory/service.py` (`worth_extracting`) |
| 10 | Boot chain, DI, factory de tools | Novos recursos entram na mesma cadeia | `boot.py`, `agent/tools/__init__.py` |
| 10 | `recursion_limit`, pool HTTP compartilhado | Limite por turno e um `httpx.AsyncClient` para todos os clientes | `agent/runner.py`, `boot.py` |
| 11 | `session` / `interaction` / `sequence` / tombstone | Transcript durável: a conversa sobrevive ao TTL | `memory/conversation_store.py` |
| 11 | Persistir evento terminal, nunca delta | Grava só `on_chat_model_end` e `on_tool_end` | `agent/runner.py` |
| 11, 12 | `fact` / `profile` por similaridade, fora do caminho crítico | Memória de longo prazo entre conversas | `memory/service.py`, nó `recall` do grafo |
| 12 | Memória editável; memória é vetor de ataque | Painel de memórias; filtro e prompt de defesa | `MemoryPanel.tsx`, `memory/service.py` |
| 14 | Parsing, chunk recursivo, contrato do chunk, 202 + worker, idempotência | Ingestão de `.md` e `.txt` | `rag/` |
| 14 | Enriquecimento contextual | Opcional (`RAG_ENRICH`), porque custa uma chamada por chunk | `rag/service.py` |
| 15 | Reprocessar só o que mudou | Hash por chunk: reenvio só reembeda o que mudou (a ideia da Merkle tree, sem a árvore) | `rag/service.py` |
| 16 | HNSW com `m` e `ef_construction` | Índice no Redis, reconstruível a partir do SQLite | `rag/vector_index.py` |
| 16 | Top-k sem threshold em RAG; threshold em memória | Os dois comportamentos, cada um onde o curso usa | `rag/service.py`, `memory/service.py` |
| 16 | Progressive disclosure, runtime context | Tools pequenas e `<runtime_context>` no system prompt | `agent/tools/knowledge.py`, `agent/prompts.py` |
| 17 | Eval offline, evaluators, Recall@K, LLM-as-a-judge | Dataset por cenário, comparação com a última run | `backend/evals/` |
| 17 | Eval online, annotation queue | 👍/👎 por resposta; 👎 vira item de dataset | `POST .../feedback`, `evals/export_feedback.py` |
| 18 | MCP server (JSON-RPC, `tools/list`, token próprio) | Base de conhecimento exposta a Claude Code e Cursor | `api/mcp.py` |
| 18 | MCP client, `tools/list` cacheado, filtro por glob | Tools de servidores externos, desligado por padrão | `agent/tools/mcp_client.py` |
| 19 | Subagente: `done` + resumo, prompt, tools e modelo próprios | Pesquisa delegada que não polui o contexto do orquestrador | `agent/subagents.py` |

## Ficou parcial

| Aula | Tema | O que falta |
|---|---|---|
| 02, 10 | HTTP/2 no cliente | Falta o pacote `h2` (`httpx[http2]`). Hoje é HTTP/1.1 com pool compartilhado |
| 14 | Parsing de PDF | Falta uma lib de PDF. Hoje aceita `.md` e `.txt` |
| 18 | OAuth no MCP | O servidor usa bearer token próprio. OAuth completo só faz sentido quando sair do localhost |
| 20 | Live Grokbot | Sem transcrição em 30/10. Só a pré-aula (19) orientou o que foi feito |

## Ficou de fora, de propósito

| Aula | Tema | Por quê |
|---|---|---|
| 19 | Multiagente | A tarefa aqui se decompõe, então subagente basta. Pela regra da própria aula, multiagente exigiria colaboração real |
| 18 | Workflow por classificador | O chat tem um agente só, sem steps conhecidos |
| 16, 17 | Decision models | Exigem treinar e calibrar um modelo próprio |
| 15, 16 | GraphRAG, ontologia, Steiner tree, text-to-SQL | Não há domínio com relações tipadas nem banco para consultar |
| 16 | Re-ranking | O curso pede evidência antes. Só vale se o Recall@K mostrar que falta |
| 16 | Threshold em RAG | O curso prefere não usar sem evidência |
| 15 | Multimodal, visual tokens | Sem caso de uso aqui, e imagem custa caro |
| 17 | AI platform (agente versionado em banco) | É produto à parte; aqui o agente é um só e fica no git |
| 11 | Fork, rewind, share | Dependem de autenticação e de múltiplos usuários |
| 12 | Auth, authz, multitenant | O app roda em localhost com um usuário. A coluna `user_id` já existe para quando sair |
| 03 | Fine-tuning | "Dado antes de prompt antes de fine-tune" |
