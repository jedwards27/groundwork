"""The web client's types are generated from web/openapi.json; this fails when they are stale.
Regenerate with `make types`."""

import json

from groundwork.api.app import app
from groundwork.config import REPO_ROOT


def test_web_openapi_is_current():
    committed = REPO_ROOT / "web" / "openapi.json"
    assert committed.exists(), "run `make types`"
    assert json.loads(committed.read_text()) == json.loads(json.dumps(app.openapi())), "run `make types`"
