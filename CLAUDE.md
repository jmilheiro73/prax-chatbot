# Contexto para o Claude Code

## Como trabalhar com o Juan

- O Juan está estudando o código para continuar o desenvolvimento. Explique em português, de forma curta.
- Formato preferido: um passo por linha, com tracinho. Sem detalhar além do que foi perguntado.
- Não suba serviços nem rode setup por ele (`docker compose`, `./dev.sh`, `uv sync`, `npm install`),
  a menos que ele peça explicitamente. Mostre o comando e diga em uma linha o que ele faz.
  Leitura de código e `git status` estão liberados.
- Quando ele resumir um fluxo com as próprias palavras, valide: diga o que está certo e corrija só o que está errado.

## Ambiente local

- Redis 8 roda via Docker e precisa estar no ar antes do `./dev.sh`: `docker compose up -d`.
- Redis Insight em http://localhost:5540. Na conexão, o host é `prax-redis` (não `127.0.0.1`).
- O `.env` fica na raiz e não vai para o git. Na máquina nova, copie de `.env.example` e preencha as chaves.

## Estado do repo (2026-10-30)

- GitHub: `jmilheiro73/prax-chatbot`, público. O nome antigo era `praxis-chatbot`.
- Branch de trabalho: `main`. A `docs/readme` está desatualizada e já foi toda para a `main`.
- "praxis" virou "prax" no código: containers `prax-redis` e `prax-redisinsight`, run `prax-chatbot` no LangSmith,
  chave `prax-chatbot:thread_id` no localStorage.
- Redis e Redis Insight só escutam em `127.0.0.1` (`docker-compose.yml`).
- O `postcss` é forçado para `^8.5.23` pelo `overrides` do `frontend/package.json`, porque o `next` 15 fixa a 8.4.31,
  que tem falhas. Subir para o `next` 16 é mudança grande; não faça sem planejar.
- No GitHub estão ligados: Secret Protection, Push protection, Dependabot alerts e Dependabot security updates.
- O front segue o visual do ChatGPT, mas com fundo preto no tema escuro, a pedido do Juan (2026-10-30).
  Não ponha botão que o back não suporta. A marca é só o texto "Prax", sem símbolo (ele testou várias versões e não quis).
- Com `CHECKPOINT_TTL_SECONDS=60` (valor de teste do `.env`), o agente esquece a conversa em 1 minuto. A tela continua
  mostrando, porque vem do transcript durável, e avisa.
- Em 2026-10-30 entraram: transcript durável, memória de longo prazo, RAG, subagente, MCP e evals. O mapa de cada aula para
  o código, e do que ficou de fora, está em `docs/mapa-aulas.md`.
- A tool de clima continua stub: sempre 22°C. Trocar por clima real quebra o AC-03 e o AC-08; o Juan ainda não decidiu.
- A live da Semana 10 (Grokbot) não tinha transcrição em 30/10. Quando sair, conferir se muda algo em `agent/subagents.py`.
- A `main` já tem o `opentelemetry-api` 1.45.1 (commit `4af7acf`). A branch remota
  `dependabot/uv/backend/opentelemetry-api-1.45.1` sobrou e pode ser apagada (ainda não foi, falta o Juan autorizar).

## Limitações conhecidas (2026-10-30)

- Resposta cortada pelo botão parar some ao recarregar: o transcript só grava evento terminal.
- Depois de parar, o modelo pode responder à pergunta pendente no turno seguinte.
- Com documento na base, o agente também busca em perguntas gerais.
- O cliente MCP nunca foi testado contra um servidor externo real.
- O que ficou parcial por aula (HTTP/2, PDF, OAuth no MCP) está em `docs/mapa-aulas.md`.

## Memória do Claude

- A memória do Claude (`~/.claude/projects/.../memory/`) não sincroniza entre as máquinas.
  O que a outra máquina precisa saber vai neste arquivo ou em `docs/`, com commit e push na `main`.
- A memória deste projeto viaja no repo privado `praxis-ai-engineering`, pelo `memoria-assistente/sincronizar.sh`:
  `salvar` antes do push ao sair, `restaurar` depois do `git pull` ao chegar.

## Ao chegar em outra máquina (que já tinha o projeto)

- `git status` antes de tudo. Se tiver mudança ou commit não enviado, o `git pull` pode dar conflito
  por causa da troca de "praxis" para "prax".
- `git remote set-url origin https://github.com/jmilheiro73/prax-chatbot.git`: aponta o git para o nome novo.
- `git checkout main && git pull`: baixa tudo.
- `cd frontend && npm install`: instala o `next` e o `postcss` novos.
- `cd backend && uv sync`: instala as dependências novas no `.venv` (`redisvl`, `numpy`, `httpx`).
- `docker rm -f praxis-redis praxis-redisinsight`: apaga os containers com o nome antigo, se existirem.
  Depois, `docker compose up -d`.
- No Redis Insight, edite a conexão salva para o host `prax-redis`.
- No `.env`, troque `LANGSMITH_PROJECT` para `prax-chatbot` se quiser os runs no projeto novo.
  As variáveis novas (RAG, memória, MCP) têm default: o `.env` antigo continua valendo.
- `backend/data/` e o Redis não vão para o git: conversas, memórias e documentos começam vazios na outra máquina.

## Máquina nova (clone do zero)

- Precisa de Docker (com o plugin compose), `uv` e `node` 22.
- `cp .env.example .env`: cria o `.env`. Preencha `OPENAI_API_KEY` e `LANGSMITH_API_KEY`.
- `cd backend && uv sync`: cria o `.venv` com as dependências Python.
- `cd frontend && npm install`: instala as dependências do front.
- `docker compose up -d`: sobe Redis e Redis Insight.
- `./dev.sh`: sobe a API (:8000) e o front (:3000).

## Onde o estudo parou

- Notas em `docs/estudo-fluxo.md`.
- 2026-10-25 e 2026-10-26: sem estudo. Foram renomeação, segurança e sincronização entre máquinas.
- 2026-10-27: `ExecuteRequest`, `Depends(get_runner)`, injeção de dependência vs. global, `lifespan`,
  `Settings` (como lê o `.env`, variável faltando, `alias`).
- 2026-10-30: sem estudo. Foi desenvolvimento, e o fluxo mudou: o resumo está no fim de `docs/estudo-fluxo.md`.
- Próximo: `backend/app/agent/runner.py` (`runner.stream` e `snapshot`).
- A conferir: se os runs aparecem no LangSmith. O `lifespan` agora copia o `LANGSMITH_*` para o `os.environ`
  (`settings.export_tracing_env()`), mas falta ver um run chegar de verdade.
