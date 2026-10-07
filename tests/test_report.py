from pathlib import Path

import pytest

from tm_advisor.report.render import render_html, render_pdf
from tm_advisor.report.sample import sample_report

CHROMIUM = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"


def test_sample_report_has_every_section_and_escapes_text():
    report = sample_report()
    html = render_html(report)
    for heading in ("1. Summary", "2. Recommended route", "3. Distinctiveness (section 41)",
                    "4. Similar marks (section 44)", "5. Your goods and services", "6. Designing your composite mark",
                    "7. How to file", "8. When to get an attorney", "9. About this report"):
        assert heading in html, heading
    assert "Sample report" in html
    assert "#2536546" in html and "search.ipaustralia.gov.au/trademarks/search/view/2536546" in html
    assert "<s>hosting of websites</s>" in html
    assert "A$660 in total for 2 classes" in html

    nasty = report.model_copy(update={"mark": "<script>alert(1)</script>"})
    assert "<script>alert(1)</script>" not in render_html(nasty)


def test_sections_renumber_without_design_guidance():
    html = render_html(sample_report().model_copy(update={"design_guidance": [], "sample": False}))
    assert "Designing your composite mark" not in html and "6. How to file" in html
    assert "Sample report" not in html


def test_pdf_renders(tmp_path):
    pytest.importorskip("playwright")
    if not Path(CHROMIUM).exists():
        pytest.skip("no Chromium here")
    out = render_pdf(sample_report(), tmp_path / "r.pdf", executable_path=CHROMIUM)
    data = out.read_bytes()
    assert data.startswith(b"%PDF") and len(data) > 20_000
