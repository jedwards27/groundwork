"""The evidence envelope every connector produces.

A connector's only job is to deliver evidence with provenance. ``blob_location`` says where the
bytes live: ``inline`` (in our database), ``tenant_store`` (the org's own storage) or
``pointer_only`` (we keep derived facts and a hash; the bytes never leave the source system).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

SourceKind = Literal["file_drop", "email", "schedule_export", "portal", "instrument", "manual"]
BlobLocation = Literal["inline", "tenant_store", "pointer_only"]
Provenance = Literal["public", "synthetic", "assumption_to_verify"]
PROVENANCE_VALUES: tuple[str, ...] = ("public", "synthetic", "assumption_to_verify")


@dataclass(frozen=True)
class Envelope:
    source_kind: SourceKind
    external_ref: str
    content_hash: str
    fetched_at: datetime
    blob_location: BlobLocation = "inline"
    provenance: Provenance = "synthetic"
    media_type: str = "text/plain"

    @classmethod
    def for_file(cls, path: Path, root: Path, provenance: Provenance = "synthetic") -> Envelope:
        data = path.read_bytes()
        suffix = path.suffix.lower()
        media = {
            ".csv": "text/csv",
            ".yaml": "application/yaml",
            ".yml": "application/yaml",
            ".eml": "message/rfc822",
            ".md": "text/markdown",
        }.get(suffix, "application/octet-stream")
        return cls(
            source_kind="file_drop",
            external_ref=str(path.relative_to(root)),
            content_hash="sha256:" + hashlib.sha256(data).hexdigest(),
            fetched_at=datetime.now(UTC),
            media_type=media,
            provenance=provenance,
        )
