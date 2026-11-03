#!/bin/sh
# Start Groundwork's tool server for the Claude app (MCP over stdio), plus the Groundwork app (the web app, on 127.0.0.1).
# Needs uv (https://docs.astral.sh/uv/); uv fetches Python 3.12 and the dependencies on first run.
# `start.sh prepare` only installs, so a session-start hook can warm the environment.
set -eu
ROOT="${CLAUDE_PLUGIN_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
if [ -d "$ROOT/app/backend" ]; then APP="$ROOT/app"; else APP="$(cd "$ROOT/.." && pwd)"; fi
DATA="${CLAUDE_PLUGIN_DATA:-$HOME/.groundwork/plugin-data}"
mkdir -p "$DATA"
# Apps started from the Dock don't get the shell's PATH, so look where installers put uv,
# then ask a login shell.
UV="$(command -v uv 2>/dev/null || true)"
for c in "$HOME/.local/bin/uv" "$HOME/.cargo/bin/uv" /opt/homebrew/bin/uv /usr/local/bin/uv \
         /Library/Frameworks/Python.framework/Versions/*/bin/uv; do
  if [ -z "$UV" ] && [ -x "$c" ]; then UV="$c"; fi
done
if [ -z "$UV" ] && [ -x /bin/zsh ]; then UV="$(/bin/zsh -lc 'command -v uv' 2>/dev/null || true)"; fi
if [ -z "$UV" ]; then
  echo "Groundwork needs uv. Install it with: curl -LsSf https://astral.sh/uv/install.sh | sh" >&2
  exit 1
fi
export UV_PROJECT_ENVIRONMENT="$DATA/venv"
if [ "${1:-}" = "prepare" ]; then
  exec "$UV" sync --quiet --frozen --no-dev --extra local --python 3.12 --project "$APP/backend"
fi
exec "$UV" run --quiet --frozen --no-dev --extra local --python 3.12 --project "$APP/backend" groundwork mcp
