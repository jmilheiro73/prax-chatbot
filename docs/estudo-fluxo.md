# Estudo do fluxo do backend

Anotações de estudo de 2026-10-20 e 2026-10-27.

## Subida do servidor (roda uma vez)

- `./dev.sh` roda `uvicorn app.main:app` em `backend/`.
- O Python importa `app/main.py`, que importa `app/api/agent.py`.
- `router = APIRouter(prefix="/agent")` cria o objeto `router` em memória, com a lista `router.routes` vazia.
- O decorator `@router.post("/execute")` registra em `router.routes` a rota POST `/execute`, que aponta para a função `execute`.
- `app = create_app()` cria o objeto `app` do FastAPI.
- `app.include_router(agent_router)` copia as rotas para `app.routes` com o prefixo `/agent`.
- O `lifespan` roda `boot()`: settings, SQLite do resumo, Redis (checkpointer), LLM, tools e runner.
- O runner fica guardado em `app.state.resources`.

## Uma mensagem (roda a cada POST)

- **POST:** o front manda `{message, thread_id}` para `/agent/execute`.
- **Rota:** o FastAPI acha `execute` em `app.routes`, valida o JSON contra `ExecuteRequest` e chama `execute`.
- **Runner:** `runner.stream` chama o grafo com `astream_events` e só deixa passar eventos de LLM e de tool.
- **Redis:** o grafo carrega o histórico da thread.
- **compact:** se o histórico passou do limite de tokens, resume, salva no SQLite e apaga as mensagens antigas.
- **model:** monta o system prompt com o resumo e chama a LLM, que pede a tool `get_weather`.
- **tools:** executa `get_weather` e devolve 22°C para o `model`.
- **model de novo:** a LLM lê o resultado e responde em texto.
- **SSE:** cada evento vira um frame `event:`/`data:` e sai na hora pela conexão aberta.
- **Front:** `readSse` lê os frames e o reducer atualiza a tela.

## Pontos que confundiram e foram corrigidos

- O decorator e o `include_router` rodam só na subida. O POST não passa por eles, só usa `app.routes`.
- O objeto `app` (variável em `main.py`) não é a pasta `app/`.
- No POST nada é lido do disco. Tudo já está em memória desde a subida.
- Rota e runner ficam antes do grafo. A tool é um nó dentro do grafo.
- O Redis salva o estado depois de cada nó, não só no fim.
- O SSE roda junto com o grafo. Cada evento sai no momento em que nasce.
- No Redis os dados não estão criptografados. Estão serializados em msgpack.

## Arquivos de cada parte

| Parte | Arquivo |
|---|---|
| Rota e SSE | `backend/app/api/agent.py` |
| Subida dos recursos e Redis | `backend/app/boot.py` |
| Runner | `backend/app/agent/runner.py` |
| Grafo, estado e gatilho do resumo | `backend/app/agent/graph.py` |
| System prompt com o resumo | `backend/app/agent/prompts.py` |
| Tool | `backend/app/agent/tools/weather.py` |
| Front | `frontend/app/page.tsx` e `frontend/lib/` |

## Rota, dependência e config (2026-10-27)

### `ExecuteRequest` (`backend/app/api/agent.py`)

- `message` é obrigatório, tem que ser string e não pode ser vazio (`min_length=1`).
- Número não vira string: `{"message": 123}` falha.
- `thread_id` é opcional (string ou `null`). Se não vier, o `execute` gera um `uuid4`.
- Campo a mais no JSON é ignorado.
- Se falhar, o FastAPI responde 422 com a lista de erros e nem chama o `execute`.

### `Depends(get_runner)`

- O FastAPI chama `get_runner(request)` antes do `execute` e passa o resultado no parâmetro `runner`.
- `get_runner` lê `request.app.state.resources.runner`, que o `lifespan` guardou na subida.
- Por que não variável global: o runner só existe depois do `lifespan` (precisa abrir Redis e SQLite),
  e o teste troca o runner sem Redis nem OpenAI (`make_app` em `tests/test_api.py`).

### `lifespan` (`backend/app/boot.py`)

- Função com um `yield` no meio.
- Antes do `yield`: roda uma vez na subida (`boot()` abre SQLite, Redis, LLM e runner).
- Depois do `yield`: roda no desligamento e fecha as conexões.

### `Settings` (`backend/app/settings.py`)

- O `BaseSettings` procura cada campo nas variáveis de ambiente e no `.env` da raiz (`ROOT_ENV`).
- Ordem: variável do terminal > `.env` > `default` do campo.
- Converte o tipo: `CHECKPOINT_TTL_SECONDS=60` vira `int`. Texto não numérico dá erro.
- Variável que falta: se o campo tem `default`, usa o default. Se não tem (`OPENAI_API_KEY`), dá
  `Field required` em `load_settings()`, dentro do `create_app()`, e a API nem sobe.
- `OPENAI_API_KEY=` vazio passa no `Settings`, mas o `ChatOpenAI` falha no `boot()` ("Missing credentials").
- `alias` é o nome de fora: no código é `settings.openai_api_key`, no `.env` é `OPENAI_API_KEY`.
  O alias não é a variável. É o nome que o Pydantic procura.
- `extra="ignore"`: variável no `.env` sem campo no `Settings` é ignorada.

### A conferir

- O `Settings` lê o `.env`, mas não joga os valores no `os.environ`. O `./dev.sh` também não.
  Então o SDK do LangSmith pode não ver o `LANGSMITH_*` do `.env`. Teste: rodar o `./dev.sh`,
  mandar uma mensagem e ver se o run aparece no LangSmith.
- O README ("Problemas comuns") diz que chave vazia dá erro de validação. Não dá: o erro é no `boot()`.

## Próximo passo

- `backend/app/agent/runner.py`: o que o `runner.stream` faz com o `astream_events` e o que o `snapshot` devolve.
