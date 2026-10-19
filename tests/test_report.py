from pathlib import Path

import pytest

from tm_advisor.report.render import render_html, render_pdf
from tm_advisor.report.sample import sample_report

CHROMIUM = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"


def test_sample_report_has_every_section_and_escapes_text():
    report = sample_report()
    html = render_html(report)
    for heading in ("Summary of findings", "1. How the findings relate to each filing format",
                    "2. Distinctiveness (section 41)", "3. Similar marks (section 44)",
                    "4. Your goods and services, as you selected them", "What examiners look at in a design",
                    "5. What this research can't tell you", "6. Further research paths", "7. How filing works",
                    "8. About this report"):
        assert heading in html, heading
    assert "Sample report" in html
    assert "#2536546" in html and "search.ipaustralia.gov.au/trademarks/search/view/2536546" in html
    assert "hosting of websites" in html and "To think about" in html
    assert "A$660 in total for 2 classes" in html

    nasty = report.model_copy(update={"mark": "<script>alert(1)</script>"})
    assert "<script>alert(1)</script>" not in render_html(nasty)


def test_design_notes_only_when_relevant():
    html = render_html(sample_report().model_copy(update={"design_guidance": [], "sample": False}))
    assert "What examiners look at in a design" not in html and "7. How filing works" in html
    assert "Sample report" not in html


def test_pdf_renders(tmp_path):
    pytest.importorskip("playwright")
    if not Path(CHROMIUM).exists():
        pytest.skip("no Chromium here")
    out = render_pdf(sample_report(), tmp_path / "r.pdf", executable_path=CHROMIUM)
    data = out.read_bytes()
    assert data.startswith(b"%PDF") and len(data) > 20_000
