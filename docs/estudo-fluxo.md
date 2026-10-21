# Estudo do fluxo do backend

Anotações de estudo de 2026-10-20.

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

## Próximo passo

- Entender o JSON do `ExecuteRequest`: o que o Pydantic valida e o que acontece quando falha.
- Depois, o `Depends(get_runner)`: como o runner chega até a função `execute`.
