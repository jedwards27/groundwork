"""One server for the web app and its API, hosted or on this computer.

- ``/api/...``: the HTTP API (``api/app.py``), signed in by cookie or bearer token.
- ``/p/<token>/...``: the plugin's hand-off into the app, and the outbound guard (local only).
- ``/health``: liveness, for the platform's checks.
- everything else: the built web app (``web/dist``), a page app that routes in the browser.

The browser sees one origin, so the session cookie is first-party, no proxy holds tokens, and the
plugin needs no Node at runtime: only Python serves anything.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response

from groundwork.api.app import app as api_app
from groundwork.api.app import health
from groundwork.config import get_settings

# The page's scripts and styles come only from this origin. Base Web's styling engine writes its
# rules into <style> tags at runtime, hence 'unsafe-inline' for styles (never for scripts).
CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; "
    "font-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
)
HEADERS = {
    "content-security-policy": CSP,
    "x-frame-options": "DENY",
    "x-content-type-options": "nosniff",
    "referrer-policy": "same-origin",
    "permissions-policy": "camera=(), microphone=(), geolocation=()",
}
LOCAL_HOSTS = ("127.0.0.1", "localhost")
NOT_BUILT = (
    "<!doctype html><meta charset=utf-8><title>Groundwork</title>"
    "<p style='font:15px system-ui;margin:40px'>The web app isn't built yet. Run <code>make web-build</code>, "
    "or <code>make web</code> for development.</p>"
)


@asynccontextmanager
async def _lifespan(_: FastAPI) -> AsyncIterator[None]:
    # A mounted app's own startup and shutdown don't run by themselves; run the API's here.
    async with api_app.router.lifespan_context(api_app):
        yield


def create(local: bool | None = None, dist: Path | None = None) -> FastAPI:
    cfg = get_settings()
    local = cfg.groundwork_local if local is None else local
    dist = dist or cfg.groundwork_web_dist
    root = FastAPI(title="Groundwork", docs_url=None, redoc_url=None, openapi_url=None, lifespan=_lifespan)

    @root.middleware("http")
    async def headers(request: Request, call_next: Any) -> Response:
        # On this computer, answer only to this computer's names: a page on another site that
        # rebinds its DNS name to 127.0.0.1 gets nothing.
        if local and request.headers.get("host", "").rsplit(":", 1)[0] not in LOCAL_HOSTS:
            return JSONResponse({"detail": "unknown host"}, status_code=421)
        response: Response = await call_next(request)
        for k, v in HEADERS.items():
            response.headers.setdefault(k, v)
        if cfg.groundwork_hosted:
            response.headers.setdefault("strict-transport-security", "max-age=31536000")
        return response

    root.get("/health")(health)
    root.mount("/api", api_app)
    if local:
        from groundwork.local.page import router as hand_off

        root.include_router(hand_off)

    index = dist / "index.html"

    @root.get("/{path:path}", include_in_schema=False)
    def web(path: str) -> Response:
        if not index.exists():
            return HTMLResponse(NOT_BUILT, status_code=503)
        file = (dist / path).resolve()
        if path and file.is_file() and file.is_relative_to(dist.resolve()):
            immutable = path.startswith("assets/")
            return FileResponse(file, headers={"cache-control": "public, max-age=31536000, immutable" if immutable else "no-cache"})
        if path.startswith(("api/", "p/")):
            return JSONResponse({"detail": "not found"}, status_code=404)
        # Any other path is a page of the app; the browser's router shows it.
        return FileResponse(index, headers={"cache-control": "no-cache"})

    return root


app = create()
