#!/bin/sh
# Groundwork's outbound guard. For a connector call that sends, replies, forwards, posts or invites,
# ask the local Groundwork page whether a recipient is on a tracked project. If so, the page records
# the call in that project's ledger and answers "deny" (dry run). Otherwise it answers {} (no
# decision), and the call goes ahead untouched. If Groundwork isn't running, this does nothing.
H="${GROUNDWORK_HOME:-$HOME/.groundwork}"
[ -f "$H/port" ] && [ -f "$H/secrets.json" ] || exit 0
PORT="$(cat "$H/port")"
TOKEN="$(sed -n 's/.*"page_token": *"\([^"]*\)".*/\1/p' "$H/secrets.json")"
[ -n "$TOKEN" ] || exit 0
curl -s -m 5 -X POST -H 'Content-Type: application/json' --data-binary @- \
  "http://127.0.0.1:$PORT/p/$TOKEN/guard" 2>/dev/null || exit 0
