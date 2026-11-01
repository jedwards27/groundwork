"""The generic packages must not know what kind of project they schedule (plan revision 4, D.4)."""

import re

from groundwork.config import REPO_ROOT

GENERIC = ["core", "policy", "ledger", "api"]
TERMS = [
    r"data.?cent(er|re)s?",
    r"datacenter",
    r"campus",
    r"building",
    r"hall",
    r"rack",
    r"IT load",
    r"kW-mo",
    r"kw_mo",
    r"energiz\w*",
    r"lease",
    r"lessee",
    r"landlord",
    r"tenants?",
    r"colocation",
    r"colo",
    r"Anthropic",
    r"Fluidstack",
    r"TeraWulf",
    r"NYSEG",
    r"NYISO",
    r"NYPA",
    r"National Grid",
    r"Kintigh",
    r"Somerset",
    r"Barker",
    r"utilit(y|ies)",
    r"AHJ",
    r"transmission owner",
    r"substation",
    r"switchgear",
    r"transformer",
    r"Procore",
    r"Autodesk",
    r"P6",
    r"Primavera",
]
PATTERN = re.compile(r"\b(" + "|".join(TERMS) + r")\b", re.IGNORECASE)


def test_generic_packages_have_no_domain_words():
    pkg = REPO_ROOT / "backend" / "groundwork"
    hits = []
    for name in GENERIC:
        for path in (pkg / name).rglob("*.py") if (pkg / name).exists() else []:
            for n, line in enumerate(path.read_text().splitlines(), 1):
                m = PATTERN.search(line)
                if m:
                    hits.append(f"{path.relative_to(pkg)}:{n}: {m.group(0)!r}")
    assert hits == [], "domain words in generic packages:\n" + "\n".join(hits)


def test_fixtures_contain_no_code():
    code = [
        p for p in (REPO_ROOT / "fixtures").rglob("*") if p.suffix in {".py", ".ts", ".js", ".sh", ".tsx"}
    ]
    assert code == []


def test_telemetry_is_off_everywhere():
    assert "NEXT_TELEMETRY_DISABLED=1" in (REPO_ROOT / ".env.example").read_text()
    compose = REPO_ROOT / "docker-compose.yml"
    if compose.exists():
        assert "NEXT_TELEMETRY_DISABLED" in compose.read_text()
