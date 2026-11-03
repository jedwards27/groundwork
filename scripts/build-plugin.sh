#!/bin/sh
# Build dist/groundwork-plugin.zip: the plugin folder plus the backend it runs (source, lockfile,
# migrations), the built web app, the demo project and the database role script. No virtual
# environment and no Node: uv builds the environment on the person's machine on first run, and the
# web app is static files the backend serves. Building needs Node; running the plugin doesn't.
# Upload the zip in the Claude app, or unzip it and run `claude --plugin-dir dist/groundwork-plugin`.
set -eu
cd "$(dirname "$0")/.."
OUT=dist/groundwork-plugin
rm -rf "$OUT" dist/groundwork-plugin.zip
(cd web && { [ -d node_modules ] || npm ci --no-fund --no-audit; } && npm run build)
mkdir -p "$OUT/app/backend" "$OUT/app/fixtures" "$OUT/app/scripts" "$OUT/app/web"
cp -R plugin/. "$OUT/"
cp -R backend/groundwork backend/migrations "$OUT/app/backend/"
cp backend/pyproject.toml backend/uv.lock backend/alembic.ini "$OUT/app/backend/"
cp -R fixtures/lake-mariner "$OUT/app/fixtures/"
cp scripts/db-setup.sql "$OUT/app/scripts/"
cp -R web/dist "$OUT/app/web/"
find "$OUT" -name __pycache__ -type d -prune -exec rm -rf {} +
find "$OUT" -name '.DS_Store' -delete
(cd dist && zip -qr groundwork-plugin.zip groundwork-plugin)
echo "built dist/groundwork-plugin.zip ($(du -h dist/groundwork-plugin.zip | cut -f1), $(find "$OUT" -type f | wc -l | tr -d ' ') files)"
