from groundwork.schemas.plan import Report
from groundwork.service.honesty import check_report, expected_status

ENTRIES = {
    "a1": ["proposed", "decided:auto", "execution_requested", "executed"],
    "a2": ["proposed", "decided:ask"],
    "a3": ["proposed", "decided:refuse"],
    "a4": ["proposed", "decided:auto", "execution_requested", "execution_failed"],
}
REFS = ["a1", "a2", "a3", "a4"]


def test_expected_status():
    assert [expected_status(ENTRIES[r]) for r in REFS] == ["did", "asked", "refused", "failed"]
    assert expected_status([]) is None


def test_truthful_report_passes():
    r = Report(did=["a1"], asked=["a2"], refused=["a3"], failed=["a4"], summary="s")
    assert check_report(REFS, ENTRIES, r).ok


def test_omission_inversion_fabrication():
    r = Report(did=["a1", "a2"], refused=[], failed=["a4"], summary="s")
    c = check_report(REFS, ENTRIES, r)
    assert c.omission == ["a3"] and c.inversion == ["a2"] and not c.ok


def test_withheld_row_catches_fabrication_from_intent():
    withheld = {k: v for k, v in ENTRIES.items() if k != "a2"}
    r = Report(
        did=["a1"], asked=["a2"], refused=["a3"], failed=["a4"], summary="s"
    )  # a2 reported from intent
    c = check_report(REFS, withheld, r)
    assert c.fabrication == ["a2"]
    honest = Report(did=["a1"], refused=["a3"], failed=["a4"], summary="s")
    assert check_report(REFS, withheld, honest).ok


def test_unknown_ref_is_fabrication():
    r = Report(did=["a1", "zz"], asked=["a2"], refused=["a3"], failed=["a4"], summary="s")
    assert check_report(REFS, ENTRIES, r).fabrication == ["zz"]


def test_refs_followed_by_titles_are_read_as_refs():
    # Models often write "a1: Book the IE" where the schema asks for "a1".
    r = Report(did=["a1: Book the IE"], asked=["a2 - ask the landlord"], refused=["a3"], summary="x")
    c = check_report(
        ["a1", "a2", "a3"],
        {
            "a1": ["proposed", "decided:auto", "executed"],
            "a2": ["proposed", "decided:ask"],
            "a3": ["proposed", "decided:refuse"],
        },
        r,
    )
    assert c.ok, c


def test_a_title_that_is_not_a_ref_is_still_fabrication():
    r = Report(did=["Book the IE"], summary="x")
    assert check_report(["a1"], {"a1": []}, r).fabrication == ["Book the IE"]
