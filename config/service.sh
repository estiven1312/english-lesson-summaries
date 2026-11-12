#!/usr/bin/env bash
set -euo pipefail
PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
source "$PROJECT_DIR/config/linux.env"
PYTHON_BIN="${PYTHON_COMMAND:-python3}"
if [[ -x "$PROJECT_DIR/.venv/bin/python" ]]; then
  PYTHON_BIN="$PROJECT_DIR/.venv/bin/python"
fi
exec "$PYTHON_BIN" "$PROJECT_DIR/scripts/configure_service.py" "$@"
