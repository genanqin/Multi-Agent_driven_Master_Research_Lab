#!/bin/zsh

set -u

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_DIR" || exit 1

pause_if_interactive() {
  if [ -t 0 ]; then
    echo ""
    read -r "reply?Press Enter to exit..."
  fi
}

fail() {
  echo ""
  echo "Error: $1"
  pause_if_interactive
  exit 1
}

echo "== Quant 4.0 Multi-Agent macOS launcher =="
echo "Project: $PROJECT_DIR"

PYTHON_BIN="$(command -v python3 || true)"
if [ -z "$PYTHON_BIN" ] && [ -x "/opt/homebrew/bin/python3" ]; then
  PYTHON_BIN="/opt/homebrew/bin/python3"
fi
if [ -z "$PYTHON_BIN" ] && [ -x "/usr/local/bin/python3" ]; then
  PYTHON_BIN="/usr/local/bin/python3"
fi
if [ -z "$PYTHON_BIN" ]; then
  fail "python3 is not installed. Please install Python 3 first."
fi

if [ ! -d ".venv" ]; then
  echo "Creating virtual environment..."
  "$PYTHON_BIN" -m venv .venv || fail "failed to create virtual environment."
fi

if ! ".venv/bin/python" - <<'PY' >/dev/null 2>&1
import fastapi, uvicorn, pandas, numpy, akshare, httpx
PY
then
  echo "Installing dependencies..."
  ".venv/bin/python" -m pip install --disable-pip-version-check --no-input -r requirements.txt || fail "failed to install dependencies. Please check your network and Python environment."
else
  echo "Dependencies already available."
fi

if [ ! -f ".env" ]; then
  if [ -f ".env.example" ]; then
    echo "Creating .env from .env.example..."
    cp .env.example .env || fail "failed to create .env."
  else
    echo "Warning: .env.example not found; continuing without .env."
  fi
fi

HOST="${APP_HOST:-127.0.0.1}"
REQUESTED_PORT="${APP_PORT:-8000}"
PORT="$REQUESTED_PORT"

PORT="$(
  HOST="$HOST" REQUESTED_PORT="$REQUESTED_PORT" ".venv/bin/python" - <<'PY'
import os
import socket

host = os.environ["HOST"]
start = int(os.environ["REQUESTED_PORT"])
for port in range(start, start + 50):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind((host, port))
    except OSError:
        sock.close()
        continue
    sock.close()
    print(port)
    break
else:
    raise SystemExit(1)
PY
)" || fail "no available local port found from $REQUESTED_PORT to $((REQUESTED_PORT + 49))."

URL="http://$HOST:$PORT"
if [ "$PORT" != "$REQUESTED_PORT" ]; then
  echo "Port $REQUESTED_PORT is busy or unavailable; using $PORT instead."
fi

echo "Starting server at $URL"
open "$URL" >/dev/null 2>&1 || true

".venv/bin/uvicorn" app.main:app --host "$HOST" --port "$PORT"
EXIT_CODE=$?
if [ "$EXIT_CODE" -ne 0 ]; then
  echo ""
  echo "Server exited with code $EXIT_CODE."
  echo "Troubleshooting:"
  echo "1. If macOS asks for network permission, allow Terminal to accept local connections."
  echo "2. Try another port: APP_PORT=8010 ./start_macos.command"
  echo "3. If dependencies are broken, delete .venv and run this script again."
  pause_if_interactive
fi

exit "$EXIT_CODE"
