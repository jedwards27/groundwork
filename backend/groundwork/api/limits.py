"""Per-visitor limits on the hosted demo. The daily caps on new copies and runs are shared by every
visitor, so without these one script could use them up for everyone. A visitor is told apart by
their address, which is kept only as a keyed hash, in daily_usage, for a day."""

from __future__ import annotations

import hashlib
import hmac

from fastapi import HTTPException, Request, status

from groundwork.config import get_settings
from groundwork.db import repo


def _visitor(request: Request) -> str:
    cfg = get_settings()
    # On Fly the proxy sets Fly-Client-IP to the caller's address; a caller can't choose it.
    ip = request.headers.get("fly-client-ip") if cfg.groundwork_hosted else None
    ip = ip or (request.client.host if request.client else "unknown")
    # The label keeps this use of the signing secret apart from signing tokens.
    message = b"groundwork visitor address:" + ip.encode()
    return hmac.new(cfg.groundwork_dev_hmac_secret.encode(), message, hashlib.sha256).hexdigest()[:16]


def claim(request: Request, what: str, cap: int, says: str) -> None:
    """Count one `what` (a new demo copy, a run) for this visitor today, or refuse with 429 once
    they've had `cap`. A cap of 0 means no limit."""
    if cap > 0 and not repo.claim_daily(f"{what}:{_visitor(request)}", cap):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, says)
