"""Groundwork running on one person's computer, inside the Claude app (the plugin).

``runtime`` starts an embedded Postgres under ``~/.groundwork`` and points the app at it.
``tools`` are the plugin's tools as plain functions; ``mcp_server`` exposes them to Claude.
``page`` opens the Groundwork app (the same web app as the hosted demo, served by ``api/server.py``) from Claude's links; there the named person approves, confirms drafts and reads the ledger.
``guard`` holds outbound connector calls addressed to a party on a tracked project.

Claude proposes; the gateway decides; only a person in the Groundwork app approves or confirms.
"""
