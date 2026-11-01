"""Dev identity: HMAC-signed bearer tokens for seeded people.

Format ``gw1.<kid>.<payload>.<sig>``: payload is base64url JSON ``{"pid","org","exp"}``, sig is
HMAC-SHA256 over ``gw1.<kid>.<payload>`` with the secret in ``GROUNDWORK_DEV_HMAC_SECRET``. The
``kid`` is derived from the secret, so rotating the secret invalidates every token.

This is a credential, not real authentication: anyone with the secret can mint a token for any
person, so the secret is the trust root in development. In production the org's identity
provider replaces it, and approvals above a threshold require fresh authentication. The ledger
stores ``person_id`` and ``kid``, never a token.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta


class TokenError(ValueError):
    pass


@dataclass(frozen=True)
class Identity:
    person_id: uuid.UUID
    org_id: uuid.UUID
    kid: str
    expires_at: datetime


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def key_id(secret: str) -> str:
    return "dev-" + hashlib.sha256(secret.encode()).hexdigest()[:8]


def mint(
    person_id: uuid.UUID, org_id: uuid.UUID, *, secret: str, ttl_hours: int, now: datetime | None = None
) -> str:
    if not secret:
        raise TokenError("GROUNDWORK_DEV_HMAC_SECRET is not set (run `make setup`)")
    now = now or datetime.now(UTC)
    kid = key_id(secret)
    payload = _b64(
        json.dumps(
            {
                "pid": str(person_id),
                "org": str(org_id),
                "exp": int((now + timedelta(hours=ttl_hours)).timestamp()),
            },
            separators=(",", ":"),
        ).encode()
    )
    signing = f"gw1.{kid}.{payload}"
    sig = _b64(hmac.new(secret.encode(), signing.encode(), hashlib.sha256).digest())
    return f"{signing}.{sig}"


def verify(token: str, *, secret: str, now: datetime | None = None) -> Identity:
    if not secret:
        raise TokenError("server has no signing secret")
    parts = token.split(".")
    if len(parts) != 4 or parts[0] != "gw1":
        raise TokenError("malformed token")
    _, kid, payload, sig = parts
    if not hmac.compare_digest(kid, key_id(secret)):
        raise TokenError("token was signed with a different key")
    expected = _b64(hmac.new(secret.encode(), f"gw1.{kid}.{payload}".encode(), hashlib.sha256).digest())
    if not hmac.compare_digest(sig, expected):
        raise TokenError("bad signature")
    data = json.loads(_unb64(payload))
    exp = datetime.fromtimestamp(int(data["exp"]), UTC)
    if (now or datetime.now(UTC)) >= exp:
        raise TokenError("token expired")
    return Identity(uuid.UUID(data["pid"]), uuid.UUID(data["org"]), kid, exp)
