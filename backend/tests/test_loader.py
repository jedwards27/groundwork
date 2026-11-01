import shutil

import pytest

from groundwork.ingest import LoadError, load_site
from groundwork.ingest.site_loader import parse_predecessors


def test_predecessor_notation():
    problems: list[str] = []
    links = parse_predecessors("a; b FS+15bd; c FF+5bd; d SS-2cd", "x", problems)
    assert problems == []
    assert [(ln.pred, ln.kind, ln.lag, ln.lag_calendar) for ln in links] == [
        ("a", "FS", 0, "business"),
        ("b", "FS", 15, "business"),
        ("c", "FF", 5, "business"),
        ("d", "SS", -2, "calendar"),
    ]


def test_all_problems_are_reported_together(tmp_path, fixture_dir):
    site = tmp_path / "site"
    shutil.copytree(fixture_dir, site)
    csv = (site / "schedule.csv").read_text().splitlines()
    csv[1] = csv[1].replace(",permit,", ",paperwork,")  # bad kind
    csv[2] = csv[2].replace("terawulf", "nobody", 1)  # unknown owner
    csv.append(
        "orphan,orphan,Orphan,study,terawulf,terawulf,not_started,2026-12-01,2026-11-01,,business,ghost,synthetic,,"
    )
    (site / "schedule.csv").write_text("\n".join(csv) + "\n")
    with pytest.raises(LoadError) as exc:
        load_site(site)
    text = "\n".join(exc.value.problems)
    assert "kind 'paperwork'" in text
    assert "'nobody' is not a party" in text
    assert "after planned_finish" in text
    assert "'ghost' is not an item" in text
