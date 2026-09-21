from pathlib import Path

import pytest

from tpg.ingest import ingest, segment

FIX = Path(__file__).parent / "fixtures"


@pytest.mark.parametrize("name", ["sample.md", "sample.html", "sample.docx", "sample.pdf"])
def test_sample_segments_into_known_clauses(name):
    clauses = ingest(str(FIX / name))
    ids = [c.id for c in clauses]
    assert ["1", "5.1", "5.2", "5.3"] == [i for i in ids if i in ("1", "5.1", "5.2", "5.3")]
    c51 = next(c for c in clauses if c.id == "5.1")
    assert c51.title == "Response time"
    assert "within 500 ms" in c51.text
    c52 = next(c for c in clauses if c.id == "5.2")
    assert "shall not process" in c52.text


def test_html_ignores_script():
    text = " ".join(c.text + c.title for c in ingest(str(FIX / "sample.html")))
    assert "var x" not in text


def test_iso_style_number_on_own_line_is_joined():
    pages = ["7.4.2\t\nBiometric template\nThe template shall be present.\n7.5\t Country codes\nCodes shall follow ISO 3166."]
    clauses = segment(pages)
    assert [(c.id, c.title) for c in clauses] == [("7.4.2", "Biometric template"), ("7.5", "Country codes")]


def test_nbsp_after_number_is_accepted():
    clauses = segment(["5.1.\xa0\xa0New Parameters\nThe wallet shall accept them."])
    assert clauses[0].id == "5.1" and clauses[0].title == "New Parameters"


def test_page_footer_is_not_a_heading():
    clauses = segment(["3 of 77\nSome body text that shall be kept."])
    assert all(c.id != "3" for c in clauses)


def test_no_headings_falls_back_to_pages():
    clauses = segment(["first page text", "second page text"])
    assert [c.id for c in clauses] == ["p1", "p2"]
    assert clauses[1].text == "second page text"


def test_long_line_is_not_a_heading():
    line = "5 " + "x" * 100
    clauses = segment([line])
    assert clauses[0].id == "p1"


def test_openid_pdf_has_expected_clauses():
    ids = {c.id for c in ingest(str(FIX / "OpenID4VP1-0.pdf"))}
    assert {"5", "5.1", "5.2"} <= ids


def test_rfc_pdf_falls_back_to_pages():
    clauses = ingest(str(FIX / "RFC8949.pdf"))
    assert clauses[0].id == "p1" and len(clauses) > 50


@pytest.mark.skipif(not (FIX / "iso_18013_5.pdf").exists(), reason="ISO fixture not distributed")
def test_iso_pdf_has_expected_clauses():
    ids = {c.id for c in ingest(str(FIX / "iso_18013_5.pdf"))}
    assert {"1", "6.1", "8.1", "8.1.1"} <= ids
