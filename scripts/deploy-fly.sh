#!/bin/sh
# Deploy the hosted demo to Fly.io: the API (private) and Mission Control (public).
# Before the first run: `fly auth login`, and `make hosted-bootstrap` to write .env.hosted.
# Safe to re-run: it creates the apps only if they are missing and re-imports the secrets.
# App names are global on Fly; set FLY_API_APP and FLY_WEB_APP if the defaults are taken.
set -eu
ROOT=$(cd "$(dirname "$0")/.." && pwd)
API_APP=${FLY_API_APP:-groundwork-api}
WEB_APP=${FLY_WEB_APP:-groundwork-web}
SECRETS="$ROOT/.env.hosted"

command -v fly >/dev/null 2>&1 || { echo "Install flyctl first: https://fly.io/docs/flyctl/install/"; exit 1; }
fly auth whoami >/dev/null 2>&1 || { echo "Run: fly auth login"; exit 1; }
[ -f "$SECRETS" ] || { echo "No .env.hosted. Run: make hosted-bootstrap"; exit 1; }

for app in "$API_APP" "$WEB_APP"; do
  if ! fly status -a "$app" >/dev/null 2>&1; then
    echo "creating Fly app $app"
    fly apps create "$app"
  fi
done

# Secrets are piped, never printed. The API gets every line; the web app only the admin token.
grep -E '^[A-Z_]+=' "$SECRETS" | fly secrets import --stage -a "$API_APP"
grep -E '^GROUNDWORK_ADMIN_TOKEN=' "$SECRETS" | fly secrets import --stage -a "$WEB_APP"

# The API image is built from the repo root (it needs fixtures/). One machine on purpose (ADR 0007);
# no public IPs.
cd "$ROOT"
fly deploy --config fly.toml -a "$API_APP" --ha=false --no-public-ips

# Mission Control is built from web/ and told where the API is on the private network.
cd "$ROOT/web"
fly deploy --config fly.toml -a "$WEB_APP" --ha=false --env "GROUNDWORK_API_URL=http://$API_APP.internal:8000"

echo "Mission Control: https://$WEB_APP.fly.dev"
