#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"

port_busy() {
  python3 -c "import socket; s=socket.socket(); s.bind(('127.0.0.1',$1)); s.close()" >/dev/null 2>&1 && return 1 || return 0
}

next_port() {
  local port=$1
  while port_busy "$port"; do
    port=$((port + 1))
  done
  echo "$port"
}

BACK_PORT=$(next_port 8000)
FRONT_PORT=$(next_port 3000)

echo "Backend  → http://localhost:${BACK_PORT}"
echo "Frontend → http://localhost:${FRONT_PORT}"
echo ""

# Source backend .env so secrets are current (beats stale shell env).
if [ -f backend/.env ]; then
  set -a; source backend/.env; set +a
fi

(cd backend && .venv/bin/python -m uvicorn app.main:app --reload --port "$BACK_PORT" --log-level warning) &
BACK_PID=$!

(cd frontend && API_URL="http://localhost:${BACK_PORT}" npx vite --port "$FRONT_PORT") &
FRONT_PID=$!

echo "Backend PID: $BACK_PID  |  Frontend PID: $FRONT_PID"
echo "Press Ctrl+C to stop both"

wait
