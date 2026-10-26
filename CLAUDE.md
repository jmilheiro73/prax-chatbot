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

## Estado do repo (2026-10-26)

- GitHub: `jmilheiro73/prax-chatbot`, público. O nome antigo era `praxis-chatbot`.
- Branch de trabalho: `main`. A `docs/readme` está desatualizada e já foi toda para a `main`.
- "praxis" virou "prax" no código: containers `prax-redis` e `prax-redisinsight`, run `prax-chatbot` no LangSmith,
  chave `prax-chatbot:thread_id` no localStorage.
- Redis e Redis Insight só escutam em `127.0.0.1` (`docker-compose.yml`).
- O `postcss` é forçado para `^8.5.23` pelo `overrides` do `frontend/package.json`, porque o `next` 15 fixa a 8.4.31,
  que tem falhas. Subir para o `next` 16 é mudança grande; não faça sem planejar.
- No GitHub estão ligados: Secret Protection, Push protection, Dependabot alerts e Dependabot security updates.
- Pendente: a branch `dependabot/uv/backend/opentelemetry-api-1.45.1` (1.45.0 → 1.45.1) ainda não entrou na `main`.

## Memória do Claude

- A memória do Claude (`~/.claude/projects/.../memory/`) não sincroniza entre as máquinas.
  O que a outra máquina precisa saber vai neste arquivo ou em `docs/`, com commit e push na `main`.

## Ao chegar em outra máquina (que já tinha o projeto)

- `git status` antes de tudo. Se tiver mudança ou commit não enviado, o `git pull` pode dar conflito
  por causa da troca de "praxis" para "prax".
- `git remote set-url origin https://github.com/jmilheiro73/prax-chatbot.git`: aponta o git para o nome novo.
- `git checkout main && git pull`: baixa tudo.
- `cd frontend && npm install`: instala o `next` e o `postcss` novos.
- `cd backend && uv sync`: instala o `certifi` e o `opentelemetry-api` novos no `.venv`.
- `docker rm -f praxis-redis praxis-redisinsight`: apaga os containers com o nome antigo, se existirem.
  Depois, `docker compose up -d`.
- No Redis Insight, edite a conexão salva para o host `prax-redis`.
- No `.env`, troque `LANGSMITH_PROJECT` para `prax-chatbot` se quiser os runs no projeto novo.

## Máquina nova (clone do zero)

- Precisa de Docker (com o plugin compose), `uv` e `node` 22.
- `cp .env.example .env`: cria o `.env`. Preencha `OPENAI_API_KEY` e `LANGSMITH_API_KEY`.
- `cd backend && uv sync`: cria o `.venv` com as dependências Python.
- `cd frontend && npm install`: instala as dependências do front.
- `docker compose up -d`: sobe Redis e Redis Insight.
- `./dev.sh`: sobe a API (:8000) e o front (:3000).

## Onde o estudo parou

- Notas em `docs/estudo-fluxo.md`.
- Próximo: `ExecuteRequest` (o que o Pydantic valida no JSON e o que acontece quando falha).
  Depois, `Depends(get_runner)`.
- 2026-10-25 e 2026-10-26: sem estudo. Foram renomeação, segurança e sincronização entre máquinas.
