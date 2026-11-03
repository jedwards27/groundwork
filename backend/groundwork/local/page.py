"""The way into the web app from Claude, and the outbound guard's endpoint.

The local runtime serves the same web app as the hosted demo (``api/server.py``), on 127.0.0.1.
Claude prints links of the form ``/p/<page token>/<path>``. The page token is random and kept in
``~/.groundwork/secrets.json``, so following a link proves the browser was opened from this
computer. The hand-off sets a local session cookie and sends the browser on to ``/<path>``.
"""

from __future__ import annotations

import hmac
import json
import re

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse

from groundwork.api.viewer import local_cookie
from groundwork.local import guard
from groundwork.local.home import local_secrets

router = APIRouter()

# Where a hand-off may land: the app's own pages, never another site.
SAFE_PATH = re.compile(r"^[A-Za-z0-9/_.-]*$")


def _check(token: str) -> None:
    if not hmac.compare_digest(token, local_secrets()["page_token"]):
        raise HTTPException(404)


@router.post("/p/{token}/guard")
async def guard_hook(token: str, request: Request) -> JSONResponse:
    _check(token)
    try:
        payload = await request.json()
    except json.JSONDecodeError:
        return JSONResponse({})
    return JSONResponse(guard.check(payload))


@router.get("/p/{token}/{path:path}")
def hand_off(token: str, path: str, request: Request) -> RedirectResponse:
    _check(token)
    target = "/" + path.lstrip("/") if SAFE_PATH.match(path) and ".." not in path else "/"
    if request.url.query:
        target += "?" + request.url.query
    response = RedirectResponse(target, status_code=303)
    local_cookie(request, response)
    return response
