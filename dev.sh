#!/usr/bin/env bash
# Sobe API (uvicorn, :8000) e front (next dev, :3000). Redis precisa estar no ar em REDIS_URL.
#   ./dev.sh           -> API + front
#   ./dev.sh api       -> só API
#   ./dev.sh front     -> só front
set -euo pipefail
cd "$(dirname "$0")"

[ -f .env ] || { echo "faltou .env na raiz (copie de .env.example)"; exit 1; }

api()   { (cd backend && uv run uvicorn app.main:app --reload --port 8000); }
front() { (cd frontend && npm run dev); }

case "${1:-all}" in
  api) api ;;
  front) front ;;
  all) api & front & wait ;;
esac
