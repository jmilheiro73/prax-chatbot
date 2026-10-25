# Contexto para o Claude Code

## Como trabalhar com o Juan

- O Juan está estudando o código para continuar o desenvolvimento. Explique em português, de forma curta.
- Formato preferido: um passo por linha, com tracinho. Sem detalhar além do que foi perguntado.
- Não suba serviços nem rode setup por ele (`docker compose`, `./dev.sh`, `uv sync`, `npm install`).
  Mostre o comando e diga em uma linha o que ele faz. Leitura de código e `git status` estão liberados.
- Quando ele resumir um fluxo com as próprias palavras, valide: diga o que está certo e corrija só o que está errado.

## Ambiente local

- Redis 8 roda via Docker e precisa estar no ar antes do `./dev.sh`: `docker compose up -d`.
- Redis Insight em http://localhost:5540. Na conexão, o host é `prax-redis` (não `127.0.0.1`).
- O `.env` fica na raiz e não vai para o git. Na máquina nova, copie de `.env.example` e preencha as chaves.

## Onde o estudo parou

Ver `docs/estudo-fluxo.md`.
