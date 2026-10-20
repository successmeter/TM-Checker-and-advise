"""Copies the goods & services lists from IP Australia's class pages for you, using a browser on your computer.

  py -m pip install playwright
  py -m playwright install chromium
  py -m tm_advisor.picklist_browser            all 45 classes (about 5-10 minutes), then imports them
  py -m tm_advisor.picklist_browser 1 25 35    only these classes
  py -m tm_advisor.picklist_browser --show     watch the browser while it works

The class pages (https://tmgns.search.ipaustralia.gov.au/descriptions?class=N) are built by JavaScript, so they're
opened in a real browser and the text on screen is read, exactly as you would copy it by hand, one page at a time
with a pause between classes. "Next" buttons and "load more" scrolling are followed. Each class is saved to
data/picklist_pages/N.txt and then imported into data/picklist.json (see picklist_import). Text that appears on
every class page (menus, footers) is left out.
"""

import argparse
import re
import time
from collections import Counter
from collections.abc import Callable, Iterable
from pathlib import Path

from .picklist_import import import_folder

ROOT = Path(__file__).resolve().parents[1]
PAGES = ROOT / "data" / "picklist_pages"
SITE = "https://tmgns.search.ipaustralia.gov.au"
_NEXT = re.compile(r"^\s*(next|next page|›|»|>|load more|show more|more results)\s*$", re.I)


def class_url(class_number: int, site: str = SITE) -> str:
    return f"{site}/descriptions?class={class_number}"


def visible_lines(page) -> list[str]:
    root = page.locator("main").first if page.locator("main").count() else page.locator("body")
    return [" ".join(line.split()) for line in root.inner_text().splitlines() if line.strip()]


def _settle(page) -> None:
    try:
        page.wait_for_load_state("networkidle", timeout=15000)
    except Exception:  # some pages keep a connection open; carry on after the timeout
        pass
    page.wait_for_timeout(500)


def _next_control(page):
    for role in ("button", "link"):
        control = page.get_by_role(role, name=_NEXT)
        for i in range(control.count()):
            item = control.nth(i)
            if item.is_visible() and item.is_enabled() and item.get_attribute("aria-disabled") != "true":
                return item
    return None


def read_class(page, class_number: int, site: str = SITE, max_pages: int = 300) -> list[str]:
    """Every line shown for a class, across all its pages."""
    page.goto(class_url(class_number, site))
    _settle(page)
    lines: list[str] = []
    for _ in range(max_pages):
        height = -1
        while True:  # lists that load more as you scroll
            new_height = page.evaluate("document.body.scrollHeight")
            if new_height == height:
                break
            height = new_height
            page.mouse.wheel(0, 100000)
            page.wait_for_timeout(400)
        before = len(lines)
        lines += [line for line in visible_lines(page) if line not in lines]
        control = _next_control(page)
        if control is None or len(lines) == before:
            break
        control.click()
        _settle(page)
    return lines


def drop_page_furniture(by_class: dict[int, list[str]]) -> dict[int, list[str]]:
    """Leave out lines shown on most class pages: menus, headers and footers, not goods or services."""
    if len(by_class) < 3:
        return by_class
    seen_in = Counter(line for lines in by_class.values() for line in set(lines))
    limit = max(3, len(by_class) // 2)
    return {c: [line for line in lines if seen_in[line] < limit] for c, lines in by_class.items()}


def copy_classes(classes: Iterable[int], folder: Path = PAGES, site: str = SITE, show: bool = False,
                 pause: float = 2.0, log: Callable[[str], None] = print, executable_path: str | None = None) -> dict[int, int]:
    from playwright.sync_api import sync_playwright

    folder.mkdir(parents=True, exist_ok=True)
    by_class: dict[int, list[str]] = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not show, executable_path=executable_path)
        page = browser.new_page()
        for n, class_number in enumerate(classes):
            if n:
                time.sleep(pause)
            by_class[class_number] = read_class(page, class_number, site)
            log(f"class {class_number}: read {len(by_class[class_number])} lines")
        browser.close()
    counts = {}
    for class_number, lines in drop_page_furniture(by_class).items():
        (folder / f"{class_number}.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
        counts[class_number] = len(lines)
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(prog="py -m tm_advisor.picklist_browser", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("classes", nargs="*", type=int, help="class numbers (default: all 45)")
    parser.add_argument("--show", action="store_true", help="show the browser window")
    parser.add_argument("--force", action="store_true", help="replace the picklist even if the new one is much smaller")
    args = parser.parse_args()
    try:
        import playwright  # noqa: F401
    except ImportError:
        raise SystemExit("First run:  py -m pip install playwright   and then:  py -m playwright install chromium")
    classes = [c for c in (args.classes or range(1, 46)) if 1 <= c <= 45]
    copy_classes(classes, show=args.show)
    change = import_folder(PAGES, force=args.force)
    print(f"Saved the picklist. {change.summary()}")


if __name__ == "__main__":
    main()
