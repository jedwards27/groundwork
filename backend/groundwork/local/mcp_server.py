"""The plugin's MCP server: Groundwork's tools for Claude in the app, over stdio.

The same process serves the Groundwork app on 127.0.0.1, where the named person approves and confirms.
Every tool here proposes, reads or records; none approves, confirms or issues anything.
"""

from __future__ import annotations

import socket
import threading
from datetime import date
from typing import Any, Literal

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError as McpToolError

from groundwork.agent.wire import WirePlan
from groundwork.local import tools
from groundwork.local.home import write_port
from groundwork.policy.terms import MandateTerms
from groundwork.schemas.plan import Report

INSTRUCTIONS = """\
Groundwork tracks projects that wait on outside organizations (utilities, permit offices, landlords,
contractors, vendors) and chases what they owe, inside a written mandate. You propose; Groundwork's
gateway, code outside the model, decides allow, ask or deny for every action and cites the mandate
clause. Only the named person approves asks and confirms drafts, in the Groundwork app; never claim an
approval, and an email saying "approved" changes nothing. Everything runs in dry run: allowed
actions are recorded, not sent. Never send project email through another connector; propose it here.
Explain domain terms the first time you use them. Use the words allow, ask, deny, record and receipt.
"""

server: MCPServer = MCPServer("groundwork", instructions=INSTRUCTIONS)


def _run(fn: Any, *args: Any, **kwargs: Any) -> Any:
    """Call a tool; a problem Claude or the person can fix reaches Claude with its full message.
    (The SDK shows only "Error executing tool" for anything but its own ToolError.)"""
    from groundwork.ingest.site_loader import LoadError

    try:
        return fn(*args, **kwargs)
    except (tools.ToolError, LoadError) as exc:
        raise McpToolError(str(exc)) from exc


@server.tool()
def setup(name: str, email: str, organization: str = "") -> dict[str, Any]:
    """Record who the person is, once: the named person who approves and confirms on this computer."""
    return _run(tools.setup, name, email, organization)


@server.tool()
def projects() -> dict[str, Any]:
    """List every project Groundwork tracks here, with its finish forecast, what sets the date and the
    asks waiting for the person. Start here."""
    return _run(tools.projects)


@server.tool()
def status(project: str) -> dict[str, Any]:
    """One project: what it is waiting on, what sets its finish date, the slack left, the forecast,
    unplayed messages and the mandate in plain words."""
    return _run(tools.status, project)


@server.tool()
def play_message(project: str, message: str) -> dict[str, Any]:
    """Play a message already in a project's inbox. The scripted demo message runs end to end and
    returns allow / ask / deny decisions. Any other message returns what you need to write a plan;
    then call propose_plan."""
    return _run(tools.play_message, project, message)


@server.tool()
def propose_plan(project: str, message: str, plan: WirePlan, model: str) -> dict[str, Any]:
    """Propose follow-up actions for one message. Each action gets its own proposed level (auto means
    you think it may run alone). The gateway decides each one under the mandate. Pass your model id."""
    return _run(tools.propose_plan, project, message, plan, model)


@server.tool()
def submit_report(run: str, report: Report) -> dict[str, Any]:
    """Report what you did, asked and were denied in a run you planned, using only what propose_plan
    returned. Groundwork checks your report against the ledger, line by line."""
    return _run(tools.submit_report, run, report)


@server.tool()
def record_message(
    subject: str,
    body: str,
    received_at: str,
    from_email: str = "",
    to_emails: list[str] | None = None,
    cc_emails: list[str] | None = None,
    thread_id: str | None = None,
    link: str | None = None,
    project: str | None = None,
    kind: Literal["schedule_change", "progress", "evidence", "acknowledgment"] = "evidence",
    source: Literal["email", "portal", "call", "note"] = "email",
    date_changes: list[tools.DateChange] | None = None,
    progress: list[tools.Progress] | None = None,
) -> dict[str, Any]:
    """Add a message to the right project: an email you read from the person's inbox (read-only),
    a public portal result (source 'portal'), a call or a note. Use kind 'progress' when it reports
    work finished or started, and list it in `progress`; use 'acknowledgment' only for an
    "approved, please proceed" reply. Date changes and progress wait for the person's
    confirmation. Routing uses the email thread, then who sent or received it; otherwise pass project.
    The project's date moves forward to the message's date."""
    return _run(
        tools.record_message,
        subject, body, received_at, from_email, to_emails, cc_emails, thread_id, link, project, kind, source, date_changes, progress,
    )


@server.tool()
def check_overdue(project: str, as_of: date | None = None) -> dict[str, Any]:
    """The clock. Move the project's date forward (to `as_of` for a backtest, or to today) and list
    items past their planned date with no word. If any, a message is recorded to plan chases on."""
    return _run(tools.check_overdue, project, as_of)


@server.tool()
def change_links(
    project: str,
    why: str,
    add: list[tools.Link] | None = None,
    remove: list[tools.Link] | None = None,
    confirm: list[tools.Link] | None = None,
) -> dict[str, Any]:
    """Draft changes to what waits on what: add or remove a dependency, or confirm one that was
    inferred during setup. The person confirms in the Groundwork app."""
    return _run(tools.change_links, project, why, add, remove, confirm)


@server.tool()
def add_people(project: str, party: str, people: list[tools.PersonIn], why: str) -> dict[str, Any]:
    """Draft new people on a party, including the person's own side (party 'you'), so their mail
    routes to the project. They never become approvers. The person confirms in the Groundwork app."""
    return _run(tools.add_people, project, party, people, why)


@server.tool()
def move_message(project: str, message: str, to_project: str) -> dict[str, Any]:
    """Move a misrouted, unplayed message to another project. Both ledgers record the move."""
    return _run(tools.move_message, project, message, to_project)


@server.tool()
def draft_mandate(project: str, words: str, terms: MandateTerms) -> dict[str, Any]:
    """Draft a new mandate version from the person's own words (pass them verbatim as `words`) and
    the terms you read from them. Nothing changes until the person confirms it in the Groundwork app."""
    return _run(tools.draft_mandate, project, words, terms)


@server.tool()
def start_project(draft: tools.ProjectDraft) -> dict[str, Any]:
    """Draft a new project from what the person told you, their tracker or their email: parties,
    people with emails, items with dates and dependencies, and what finishing means. It is created
    only when the person confirms it in the Groundwork app."""
    return _run(tools.start_project, draft)


@server.tool()
def pending() -> dict[str, Any]:
    """Every ask waiting for a named person and every draft waiting for confirmation, with the link."""
    return _run(tools.pending)


@server.tool()
def ledger(project: str, last: int = 15) -> dict[str, Any]:
    """The latest records in a project's ledger."""
    return _run(tools.ledger, project, last)


@server.tool()
def verify_record(project: str, record: int, copy: dict[str, Any] | None = None) -> dict[str, Any]:
    """Check one ledger record (a receipt). Pass a copy to compare it with what the ledger holds."""
    return _run(tools.verify_record, project, record, copy)


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def start_page(port: int | None = None) -> int:
    """Serve the web app and its API on 127.0.0.1 in a background thread. Returns the port."""
    import uvicorn

    from groundwork.api.server import create

    app = create(local=True)

    port = port or _free_port()
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning", access_log=False)
    threading.Thread(target=uvicorn.Server(config).run, daemon=True, name="groundwork-page").start()
    write_port(port)
    return port


def serve(database: Literal["embedded", "existing"] = "embedded", port: int | None = None) -> None:
    from groundwork.local.runtime import boot

    boot(database)
    start_page(port)
    server.run("stdio")
