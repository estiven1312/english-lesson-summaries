#!/usr/bin/env bash
set -euo pipefail
PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
case "$(uname -s)" in
  Darwin) source "$PROJECT_DIR/config/macos.env" ;;
  *) source "$PROJECT_DIR/config/linux.env" ;;
esac
PYTHON_BIN="${PYTHON_COMMAND:-python3}"
if [[ -x "$PROJECT_DIR/.venv/bin/python" ]]; then
  PYTHON_BIN="$PROJECT_DIR/.venv/bin/python"
fi
exec "$PYTHON_BIN" "$PROJECT_DIR/scripts/watch_pdfs.py" --config "${ENGLISH_CONFIG:-$PROJECT_DIR/config/job.toml}" "$@"
