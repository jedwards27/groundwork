#!/bin/sh
# Create .env from .env.example with fresh random development secrets (the token-signing secret
# and the admin token). Needs only a POSIX shell, so it works before Python or Node is installed.
# Leaves an existing .env alone.
set -eu
cd "$(dirname "$0")/.."
if [ -f .env ]; then
  echo ".env already exists; leaving it alone"
  exit 0
fi
rand() { LC_ALL=C tr -dc 'A-Za-z0-9' </dev/urandom | head -c "$1"; }
sed -e "s|^GROUNDWORK_DEV_HMAC_SECRET=.*|GROUNDWORK_DEV_HMAC_SECRET=$(rand 43)|" \
    -e "s|^GROUNDWORK_ADMIN_TOKEN=.*|GROUNDWORK_ADMIN_TOKEN=$(rand 24)|" \
    .env.example > .env
echo "created .env with fresh dev secrets (add ANTHROPIC_API_KEY to run the live planner)"
