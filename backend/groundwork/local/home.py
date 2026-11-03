"""The local home folder (``~/.groundwork`` or ``GROUNDWORK_HOME``): secrets, the person's identity,
drafts waiting for confirmation, project folders, the embedded database and the page's port."""

from __future__ import annotations

import json
import os
import re
import secrets
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


def home() -> Path:
    path = Path(os.environ.get("GROUNDWORK_HOME", "~/.groundwork")).expanduser()
    path.mkdir(parents=True, exist_ok=True)
    return path


def _read(path: Path) -> dict[str, Any] | None:
    return json.loads(path.read_text()) if path.exists() else None


def _write(path: Path, doc: dict[str, Any]) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(doc, indent=2, default=str))
    os.chmod(tmp, 0o600)
    tmp.replace(path)


def local_secrets() -> dict[str, str]:
    """Created once. The page token is the capability in the Groundwork app's address; the HMAC secret
    signs nothing that leaves the machine."""
    path = home() / "secrets.json"
    doc = _read(path)
    if doc is None:
        doc = {
            "page_token": secrets.token_urlsafe(24),
            "hmac_secret": secrets.token_urlsafe(32),
            "admin_token": secrets.token_urlsafe(24),
        }
        _write(path, doc)
    return doc


@dataclass(frozen=True)
class Me:
    """The one named person on this install: the lead and approver for their own projects."""

    name: str
    email: str
    organization: str = ""

    @property
    def key(self) -> str:
        return "me"


def me() -> Me | None:
    doc = _read(home() / "me.json")
    return Me(**doc) if doc else None


def set_me(name: str, email: str, organization: str = "") -> Me:
    who = Me(name.strip(), email.strip().lower(), organization.strip())
    if not who.name or not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", who.email):
        raise ValueError("a name and a valid email address are needed")
    _write(home() / "me.json", asdict(who))
    return who


def write_port(port: int) -> None:
    (home() / "port").write_text(str(port))


def read_port() -> int | None:
    path = home() / "port"
    return int(path.read_text().strip()) if path.exists() else None


def page_url(path: str = "") -> str:
    port = read_port() or 0
    return f"http://127.0.0.1:{port}/p/{local_secrets()['page_token']}/{path.lstrip('/')}"


def slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s[:48] or "project"
