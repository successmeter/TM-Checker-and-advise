import http.server
import threading
from pathlib import Path

import pytest

from tm_advisor.picklist_browser import copy_classes, drop_page_furniture

pytest.importorskip("playwright")
CHROMIUM = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"

# A JavaScript page like IP Australia's: terms are drawn by script, two pages per class behind a Next button.
APP = """<!doctype html><html><body><nav>Home</nav><main><h1 id=h></h1><ul id=list></ul>
<button id=next>Next</button></main><footer>Copyright IP Australia</footer><script>
const c = new URLSearchParams(location.search).get("class"); let page = 1;
function draw() {
  document.getElementById("h").textContent = "Class " + c;
  document.getElementById("list").innerHTML = [1, 2].map(i => `<li>Term ${c}-${page}-${i}</li>`).join("");
  document.getElementById("next").disabled = page >= 2;
}
document.getElementById("next").onclick = () => { page++; setTimeout(draw, 50); };
setTimeout(draw, 100);
</script></body></html>"""


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(APP.encode())

    def log_message(self, *args):
        pass


@pytest.fixture
def site():
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()


def test_reads_every_page_of_each_class_and_drops_shared_text(site, tmp_path):
    if not Path(CHROMIUM).exists():
        pytest.skip("no Chromium here")
    counts = copy_classes([1, 2, 3], tmp_path, site=site, pause=0, log=lambda _: None, executable_path=CHROMIUM)
    assert (tmp_path / "2.txt").read_text().splitlines() == [
        "Class 2", "Term 2-1-1", "Term 2-1-2", "Term 2-2-1", "Term 2-2-2"]
    assert counts == {1: 5, 2: 5, 3: 5}


def test_furniture_shared_by_most_pages_is_dropped():
    pages = {c: ["Home", "Contact us", f"Term {c}", "Shared term"] for c in range(1, 5)}
    pages[1].append("Chemicals")
    out = drop_page_furniture(pages)
    assert out[1] == ["Term 1", "Chemicals"]
