#!/bin/sh
# Deploy the hosted demo to Fly.io: one app serves the web app and its API (ADR 0007, ADR 0009).
# Before the first run: `fly auth login`, and `make hosted-bootstrap` to write .env.hosted.
# Safe to re-run: it creates the app only if it is missing and re-imports the secrets.
# App names are global on Fly; set FLY_APP if the default is taken.
set -eu
ROOT=$(cd "$(dirname "$0")/.." && pwd)
APP=${FLY_APP:-groundwork-demo}
SECRETS="$ROOT/.env.hosted"

command -v fly >/dev/null 2>&1 || { echo "Install flyctl first: https://fly.io/docs/flyctl/install/"; exit 1; }
fly auth whoami >/dev/null 2>&1 || { echo "Run: fly auth login"; exit 1; }
[ -f "$SECRETS" ] || { echo "No .env.hosted. Run: make hosted-bootstrap"; exit 1; }

if ! fly status -a "$APP" >/dev/null 2>&1; then
  echo "creating Fly app $APP"
  fly apps create "$APP"
fi

# Secrets are piped, never printed.
grep -E '^[A-Z_]+=' "$SECRETS" | fly secrets import --stage -a "$APP"

# The image is built from the repo root (it needs web/ and fixtures/). One machine on purpose (ADR 0007).
cd "$ROOT"
fly deploy --config fly.toml -a "$APP" --ha=false

echo "Groundwork: https://$APP.fly.dev"
