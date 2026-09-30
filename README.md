# praxis-chatbot — P1 + D3

Projeto pessoal da mentoria Praxis (AI Engineering). Um chatbot com agente LangGraph que:

- **P1 · Chatbot Scaffold** — `POST /agent/execute` em SSE, agente com tool de clima (stub), front Next.js
  que pinta rascunho, texto final, tool call e resultado como estados separados.
- **D3 · Memória** — duas camadas em cima do P1:
  - **curto prazo:** checkpointer do LangGraph no **Redis com TTL** (expira; o cliente manda só a mensagem atual);
  - **longo prazo:** **sumarização** da conversa acima de um limite configurável, gravada em SQLite e
    **injetada no system prompt** da chamada seguinte; tudo **traced no LangSmith**.

```
frontend (Next.js :3000)  --POST /agent/execute {message, thread_id}-->  backend (FastAPI :8000)
                          <-- text/event-stream (StreamEvent v2 inteiro por frame) --
                                                           |
                                    START -> compact -> model <-> tools -> END
                                              |            |
                                   SQLite (summary)   Redis (checkpoint, TTL)
```

## Como subir

Pré-requisitos: Python 3.12+ com [uv](https://docs.astral.sh/uv/), Node 20+, e um **Redis 8 com RediSearch**
(o checkpointer oficial `langgraph-checkpoint-redis` cria índices `FT.*`). Opções:

- `docker run -p 6379:6379 redis:8` (Redis 8 open source já traz o Query Engine), ou
- Redis instalado do repositório oficial (`packages.redis.io`), ou
- sem sudo/docker: o script `~/.local/opt/redis/run-redis.sh` desta máquina roda o `.deb` oficial extraído
  localmente com `--loadmodule redisearch.so` (é o que uso no dev).

```bash
cp .env.example .env            # preencha OPENAI_API_KEY e LANGSMITH_API_KEY
cd backend  && uv sync          # deps do back
cd ../frontend && npm install   # deps do front
cd .. && ./dev.sh               # API em :8000 + front em :3000  (ou ./dev.sh api | ./dev.sh front)
```

Abra http://localhost:3000 e pergunte **"Qual o clima em São Paulo?"** (teste de fumaça do P1, AC-08).

### Variáveis (`.env` na raiz, gitignored — P1 AC-09 / D3 AC-05)

| Variável | Padrão | Uso |
|---|---|---|
| `OPENAI_API_KEY` | — | modelo (P1) |
| `OPENAI_MODEL` | `gpt-4o-mini` | |
| `REDIS_URL` | `redis://localhost:6379` | checkpointer (D3 AC-02) |
| `CHECKPOINT_TTL_SECONDS` | `86400` (24h) | **teste: `60`** |
| `SUMMARY_TOKEN_LIMIT` | `4000` | limite do histórico antes de compactar (D3 AC-03). **teste: `10`** |
| `SUMMARY_KEEP_LAST` | `2` | mensagens recentes que sobrevivem à compactação. teste: `0` |
| `SUMMARY_DB_PATH` | `data/summaries.sqlite` | onde o summary vive |
| `LANGSMITH_TRACING` / `LANGSMITH_API_KEY` / `LANGSMITH_PROJECT` | — | tracing (D3 AC-04) |

## Valores usados no teste do D3

- **TTL do checkpoint: 60 s** (`CHECKPOINT_TTL_SECONDS=60`, com `refresh_on_read` — cada mensagem renova).
  Nos testes automatizados de integração uso 3 s.
- **Limite de compactação: 10 tokens** (`SUMMARY_TOKEN_LIMIT=10`, `SUMMARY_KEEP_LAST=0`): a partir da
  segunda mensagem qualquer histórico dispara a compactação.

Roteiro que reproduz o D3 de ponta a ponta (com a API no ar):

```bash
cd backend && uv run python smoke.py       # P1 · AC-08: tool dispara, resposta com 22°C
cd backend && uv run python smoke.py d3    # D3: longa -> compacta -> espera o TTL -> ainda lembra pelo summary
```

O `smoke.py d3` imprime o snapshot da thread em cada etapa: `checkpoint_alive=True` → summary gerado →
(espera TTL) → `checkpoint_alive=False, summary=sim` → a próxima mensagem responde só com o summary.

## Como achar o trace no LangSmith (D3 AC-04)

Projeto = `LANGSMITH_PROJECT`. Cada requisição vira um run raiz **`praxis-chatbot`** (o grafo). Dentro dele:

1. nó **`compact`** → run **`summarize_conversation`** (tag `summarizer`): o **prompt de compactação** é o
   input; o **summary** é o output. Só aparece quando o limite foi ultrapassado.
2. nó **`model`** → run `ChatOpenAI`: no input, a primeira mensagem é o **system prompt** — com o bloco
   `<conversation_summary>…</conversation_summary>` dentro quando há summary.

Ou seja: abra o run `praxis-chatbot` da 2ª mensagem, veja `summarize_conversation` (o prompt que gerou o
summary) e logo abaixo o `ChatOpenAI` do nó `model` (o system prompt com o summary injetado).

## Decisões (o que o PDF deixa em aberto)

- **Onde o summary vive:** tabela `session(thread_id, summary, compactions, …)` em SQLite
  (`backend/app/memory/summary_store.py`). Não é a coluna na sessão do case da Live 05 nem as cinco tabelas —
  é uma entidade própria, trocável por Postgres sem tocar o resto. O grafo mantém uma cópia em
  `state.summary`, mas a fonte de verdade é o banco: **quando o checkpoint expira no Redis, o summary
  continua e é recarregado** na próxima mensagem — é isso que o torna "longo prazo".
- **Quando compacta:** no início do turno (nó `compact`), olhando o histórico **sem** a mensagem atual.
  Se passou do limite: gera o summary (incorporando o anterior), grava, e remove as mensagens antigas do
  estado com `RemoveMessage`, mantendo as `SUMMARY_KEEP_LAST` mais recentes (sem deixar `ToolMessage` órfã).
- **Síncrono.** O nó roda dentro da request. É o mais simples e o que o trace mostra melhor (Live 05: "não é
  crime"; assíncrono fica para quando houver produto de voz/fila).
- **O front não vê a compactação:** a LLM do resumo tem a tag `summarizer` e o runner filtra esses eventos;
  o stream continua sendo só a conversa.
- **Contagem de tokens** com `tiktoken` local — serve para limiar, não para custo (o `usage` real fica no trace).
- **Thread:** o front guarda um `thread_id` no `localStorage` e manda `{message, thread_id}`; nunca o histórico.
  `GET /agent/threads/{id}` devolve o snapshot (checkpoint quente + summary) e hidrata a UI.

## Estrutura

```
backend/app/
  main.py            FastAPI + CORS + routers; lifespan
  boot.py            boot chain (AsyncExitStack): SQLite -> Redis saver -> LLM -> tools -> runner
  settings.py        pydantic-settings lendo ../.env
  api/agent.py       POST /agent/execute (SSE) · GET /agent/threads/{id}  — não importa LangGraph
  agent/runner.py    compila o grafo, astream_events(v2, chat_model+tool), filtra o summarizer
  agent/graph.py     nós compact / model / tools; CompactionPolicy
  agent/prompts.py   system prompt + slot do summary + prompt de compactação
  agent/tokens.py    contagem com tiktoken
  agent/tools/       factory: todo módulo com as_tool() entra (weather.py = stub, sleep 2s, 22°C)
  memory/summary_store.py  tabela session em SQLite
backend/tests/       fake LLM determinística; grafo, SSE, API, compactação, TTL real no Redis
backend/smoke.py     roteiros AC-08 e D3 contra a API
frontend/app/page.tsx      UI; lib/sse.ts (fetch + parser), lib/reducer.ts (máquina de estados), lib/events.ts (contrato)
```

## Testes

```bash
cd backend && uv run pytest -q      # 8 testes; o de TTL usa o Redis de REDIS_URL (pula se não houver)
cd frontend && npm run typecheck && npm run build
```

Também dá para subir a API inteira **sem OpenAI** (LLM falsa, Redis e SQLite reais) para testar o front:

```bash
cd backend && OPENAI_API_KEY=fake uv run uvicorn tests.e2e_app:app --port 8000
```

## Acceptance criteria

| | Onde |
|---|---|
| P1 AC-01 rota SSE que só chama o agente | `api/agent.py` |
| P1 AC-02 HTTP não importa LangGraph | `api/agent.py` (teste `test_http_layer_does_not_import_langgraph`) |
| P1 AC-03 grafo model↔tools, tool stub | `agent/graph.py`, `agent/tools/weather.py` |
| P1 AC-04 `astream_events` v2, `chat_model`+`tool` | `agent/runner.py` |
| P1 AC-05 `event:` = evento, `data:` = StreamEvent inteiro | `api/agent.py::encode_sse` |
| P1 AC-06 renderer por família; tipo desconhecido lança | `frontend/lib/reducer.ts::applyEvent` |
| P1 AC-07 tokens concatenam, `end` substitui, estados separados | `frontend/lib/reducer.ts` |
| P1 AC-08 fumaça 22°C | `backend/smoke.py` |
| P1 AC-09 / D3 AC-05 `.env` na raiz gitignored | `.env.example`, `.gitignore` |
| D3 AC-01 mesmo repo do P1 | este |
| D3 AC-02 Redis com TTL, cliente sem histórico | `boot.py`, `settings.py`, teste `test_redis_ttl.py` |
| D3 AC-03 limite configurável, summary no system prompt | `agent/graph.py::compact`, `agent/prompts.py` |
| D3 AC-04 trace mostra prompt do summary e system prompt seguinte | run `summarize_conversation` + `ChatOpenAI` do nó `model` |

## Fora de escopo (de propósito)

Transcript store de longo prazo, observations, pro knowledge, tombstone/rewind, `/finalize`, fila, CRUD de
memória na UI, RAG, Langfuse. Uma observação conhecida: como o `data:` leva o StreamEvent inteiro, o
`on_chat_model_start` expõe o system prompt (com o summary) ao cliente — é o que o AC-05 pede; em produto
real eu filtraria `data.input` antes de serializar.
