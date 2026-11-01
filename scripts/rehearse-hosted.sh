#!/bin/sh
# Rehearse the hosted profile on this machine before a real deploy (ADR 0007).
#
# Starts a throwaway Postgres whose admin role is neither superuser nor BYPASSRLS, like Neon's,
# then runs the same commands a deploy runs: `groundwork hosted-bootstrap`, `groundwork preflight`
# and `groundwork release`. It serves the API in the hosted profile on :8100 and the production web
# build on :3200. Test it from another terminal:
#
#   E2E_BASE_URL=http://localhost:3200 make e2e
#
# Needs initdb and pg_ctl (Homebrew postgresql), uv, Node 20+, and `make web-build` first.
# Ctrl-C stops everything and deletes the cluster and its secrets.
set -eu
ROOT=$(cd "$(dirname "$0")/.." && pwd)
PGPORT=${REHEARSAL_PG_PORT:-5499}
WORK=$(mktemp -d "${TMPDIR:-/tmp}/groundwork-rehearsal.XXXXXX")
rand() { LC_ALL=C tr -dc 'A-Za-z0-9' </dev/urandom | head -c 32; }

cleanup() {
  trap - EXIT INT TERM
  [ -n "${API_PID:-}" ] && kill "$API_PID" 2>/dev/null || true
  [ -n "${WEB_PID:-}" ] && kill "$WEB_PID" 2>/dev/null || true
  pg_ctl -D "$WORK/pg" -m fast stop >/dev/null 2>&1 || true
  rm -rf "$WORK"
  echo "rehearsal stopped; cluster and secrets deleted"
}
trap cleanup EXIT INT TERM

[ -f "$ROOT/web/.next/standalone/server.js" ] || { echo "Build the web app first: make web-build"; exit 1; }

echo "1/5 throwaway Postgres on :$PGPORT"
SUPER_PW=$(rand); ADMIN_PW=$(rand)
printf '%s\n' "$SUPER_PW" > "$WORK/superpw"
initdb -D "$WORK/pg" -U postgres --auth=scram-sha-256 --pwfile="$WORK/superpw" --encoding=UTF8 --locale=C >/dev/null
# TCP only: no Unix socket, whose path would be too long inside a deep temp folder on macOS.
pg_ctl -D "$WORK/pg" -o "-p $PGPORT -c listen_addresses=localhost -c unix_socket_directories=''" \
  -l "$WORK/pg.log" -w start >/dev/null || { cat "$WORK/pg.log"; exit 1; }
PGPASSWORD=$SUPER_PW psql -h localhost -p "$PGPORT" -U postgres -d postgres -v ON_ERROR_STOP=1 -q \
  -c "CREATE ROLE rehearsal_admin LOGIN CREATEROLE CREATEDB NOBYPASSRLS PASSWORD '$ADMIN_PW'"

echo "2/5 bootstrap as an admin without superuser or BYPASSRLS"
cd "$ROOT/backend"
GROUNDWORK_DB_ADMIN_URL="postgresql://rehearsal_admin:$ADMIN_PW@localhost:$PGPORT/postgres" \
  uv run groundwork hosted-bootstrap --out "$WORK/env.hosted" --sslmode disable

# The hosted environment: fly.toml's [env] (read from the file, so the rehearsal cannot drift from
# what Fly runs) plus the secrets file. Read line by line, never sourced.
uv run python -c 'import sys, tomllib; [print(f"{k}={v}") for k, v in tomllib.load(open(sys.argv[1], "rb"))["env"].items()]' \
  "$ROOT/fly.toml" > "$WORK/fly.env"
for f in "$WORK/fly.env" "$WORK/env.hosted"; do
  while IFS= read -r line; do
    case "$line" in [A-Z]*=*) export "$line" ;; esac
  done < "$f"
done
export ANTHROPIC_API_KEY=""

echo "3/5 preflight"
uv run groundwork preflight
echo "4/5 release: migrate and seed"
uv run groundwork release

echo "5/5 hosted API on :8100 (IPv6, as on Fly) and Mission Control on :3200"
uv run groundwork serve --host :: --port 8100 &
API_PID=$!
rm -rf "$ROOT/web/.next/standalone/.next/static"
cp -R "$ROOT/web/.next/static" "$ROOT/web/.next/standalone/.next/static"
(cd "$ROOT/web/.next/standalone" && exec env -i PATH="$PATH" HOME="$HOME" NODE_ENV=production \
  NEXT_TELEMETRY_DISABLED=1 PORT=3200 HOSTNAME=0.0.0.0 GROUNDWORK_API_URL="http://[::1]:8100" \
  GROUNDWORK_ADMIN_TOKEN="$GROUNDWORK_ADMIN_TOKEN" node server.js) &
WEB_PID=$!
echo "Mission Control (hosted profile): http://localhost:3200   Ctrl-C to stop"
wait
