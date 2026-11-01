import uuid
from datetime import UTC, datetime, timedelta

import pytest

from groundwork.api.auth import TokenError, key_id, mint, verify

PID, ORG = uuid.uuid4(), uuid.uuid4()


def test_round_trip():
    t = mint(PID, ORG, secret="s3cret", ttl_hours=1)
    who = verify(t, secret="s3cret")
    assert (who.person_id, who.org_id, who.kid) == (PID, ORG, key_id("s3cret"))


def test_rejects_tamper_expiry_and_rotation():
    t = mint(PID, ORG, secret="s3cret", ttl_hours=1)
    head, kid, payload, sig = t.split(".")
    with pytest.raises(TokenError):
        verify(f"{head}.{kid}.{payload[:-2]}xx.{sig}", secret="s3cret")
    with pytest.raises(TokenError, match="expired"):
        verify(t, secret="s3cret", now=datetime.now(UTC) + timedelta(hours=2))
    with pytest.raises(TokenError, match="different key"):
        verify(t, secret="rotated")
    with pytest.raises(TokenError):
        mint(PID, ORG, secret="", ttl_hours=1)
