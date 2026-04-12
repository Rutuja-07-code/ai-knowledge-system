#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8000}"
OLLAMA_URL="${OLLAMA_URL:-http://127.0.0.1:11434}"
OLLAMA_HOST_PORT="${OLLAMA_URL#http://}"
OLLAMA_HOST="${OLLAMA_HOST_PORT%%:*}"
OLLAMA_PORT="${OLLAMA_HOST_PORT##*:}"

STARTED_OLLAMA=0
OLLAMA_PID=""

cleanup() {
  if [[ "$STARTED_OLLAMA" -eq 1 && -n "$OLLAMA_PID" ]]; then
    kill "$OLLAMA_PID" >/dev/null 2>&1 || true
  fi
}

trap cleanup EXIT INT TERM

ollama_running() {
  python3 - "$OLLAMA_HOST" "$OLLAMA_PORT" <<'PY'
import socket
import sys

host = sys.argv[1]
port = int(sys.argv[2])

sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.settimeout(0.5)
try:
    sock.connect((host, port))
except OSError:
    raise SystemExit(1)
finally:
    sock.close()
PY
}

wait_for_ollama() {
  for _ in $(seq 1 30); do
    if ollama_running; then
      return 0
    fi
    sleep 1
  done

  return 1
}

if ! ollama_running; then
  if ! command -v ollama >/dev/null 2>&1; then
    echo "Ollama is not installed or not on PATH." >&2
    exit 1
  fi

  echo "Starting Ollama for this backend session..."
  ollama serve >/dev/null 2>&1 &
  OLLAMA_PID=$!
  STARTED_OLLAMA=1

  if ! wait_for_ollama; then
    echo "Ollama did not start successfully." >&2
    exit 1
  fi
fi

export AI_KNOWLEDGE_REFRESH_ON_STARTUP="${AI_KNOWLEDGE_REFRESH_ON_STARTUP:-false}"

cd "$ROOT_DIR"
exec python3 -m uvicorn src.web_server:app --host "$HOST" --port "$PORT"
