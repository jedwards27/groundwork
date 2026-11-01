"""Getting evidence in. Connectors deliver evidence in one envelope; loaders turn it into rows.

Slice 1 ships the file-drop path for a site folder (YAML + CSV). Email, PDF and portal connectors
arrive in slice 4 and produce the same envelope.
"""

from groundwork.ingest.envelope import Envelope
from groundwork.ingest.site_loader import LoadError, SiteBundle, load_site

__all__ = ["Envelope", "LoadError", "SiteBundle", "load_site"]
