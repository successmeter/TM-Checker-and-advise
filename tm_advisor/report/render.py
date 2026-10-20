"""Report HTML (the report page) and PDF (the download), from the same template."""

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from .schema import ReportDoc

TEMPLATES = Path(__file__).parent / "templates"
_env = Environment(loader=FileSystemLoader(TEMPLATES), autoescape=select_autoescape(["html"]))
KIND_LABELS = {"word": "Word mark", "composite": "Composite mark (design and words)", "logo": "Logo mark (design only)"}


def render_html(report: ReportDoc, download_url: str | None = None) -> str:
    return _env.get_template("report.html").render(r=report, kind_label=KIND_LABELS[report.mark_kind],
                                                   download_url=download_url)


def render_pdf(report: ReportDoc, out: Path, executable_path: str | None = None) -> Path:
    """A4 PDF with page numbers, rendered by headless Chromium (Playwright)."""
    from playwright.sync_api import sync_playwright

    footer = ('<div style="font-size:8px;width:100%;padding:0 16mm;color:#777;display:flex;justify-content:space-between">'
              f'<span>{report.brand} · Report {report.reference} · Register searched {report.register_searched}</span>'
              '<span>Page <span class="pageNumber"></span> of <span class="totalPages"></span></span></div>')
    out.parent.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=executable_path)
        page = browser.new_page()
        page.set_content(render_html(report), wait_until="load")
        page.pdf(path=str(out), format="A4", print_background=True, display_header_footer=True,
                 header_template="<span></span>", footer_template=footer,
                 margin={"top": "18mm", "bottom": "20mm", "left": "16mm", "right": "16mm"})
        browser.close()
    return out
