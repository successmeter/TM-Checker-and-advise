"""Builds data/picklist.json from goods & services lists copied by hand from IP Australia's class pages.

  py -m tm_advisor.picklist_import data\\picklist_pages

For each class, open https://tmgns.search.ipaustralia.gov.au/descriptions?class=N, select the list of terms, copy
it, and paste it into a text file named N.txt (1.txt ... 45.txt) in one folder: one term per line. If a class has
several pages, paste them all into the same file. Classes can be done in batches: classes already imported and
not in the folder are kept. Headings, page numbers and buttons that come along with the copy are dropped, and the
lines that were dropped are shown so you can check. Attribute IP Australia when you show the terms.
"""

import argparse
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from .picklist_sync import PicklistChange, save

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "picklist.json"
SOURCE = "IP Australia goods & services picklist (tmgns.search.ipaustralia.gov.au), copied by hand"
_NAME = re.compile(r"^(?:class)?[\s_-]*(\d{1,2})$", re.I)
# Page furniture only, matched as whole lines: real terms can start with "loading", "search", "copyright" or "showing".
_CHROME = re.compile(
    r"^(?:class\s*\d{1,2}|page\s*\d+(?:\s*of\s*\d+)?|showing\s+\d+.*|\d+\s*(?:-|to|of)\s*\d+(?:\s*of\s*\d+)?.*|"
    r"\d+\s+results?|results?|search|next|previous|prev|first|last|back|home|help|menu|close|copy|select|select all|"
    r"add|remove|download|export|print|description|descriptions|goods and services|goods & services|terms?|ok|cancel|"
    r"loading\.*|skip to (?:main )?content|ip australia|australian government|(?:copyright\s*)?©.*|privacy|disclaimer|"
    r"accessibility|notes|show detail|hide detail)$", re.I)


def _is_note(text: str) -> bool:
    """IP Australia's explanatory notes about a class, not goods or services."""
    if re.match(r"^class\s*\d{1,2}\b", text, re.I) or (len(text) > 100 and ". " in text.rstrip(".")):
        return True
    return len(text) > 300 and ";" in text and text.endswith(".")  # a class heading: "Paints, varnishes; ... ."


@dataclass
class ClassPage:
    terms: list[str]
    dropped: list[str]
    heading: str = ""
    notes: list[str] = field(default_factory=list)


def _top_section(lines: list[str]) -> tuple[int, str, list[str]]:
    """The class heading and notes at the top of a page: after "Class N", before the first term.

    Returns how many lines they take up. Headings and notes are prose (they end with a full stop or read as
    sentences); picklist terms don't.
    """
    start = next((i for i, t in enumerate(lines[:10]) if re.fullmatch(r"class\s*\d{1,2}", t, re.I)), None)
    if start is None:
        return 0, "", []
    heading, notes = "", []
    end = start + 1
    for text in lines[start + 1:]:
        if _CHROME.match(text):
            end += 1
            continue
        if not (text.endswith(".") or _is_note(text)):
            break
        if not heading and not notes and not re.match(r"^class\s*\d", text, re.I) and ". " not in text.rstrip("."):
            heading = text
        else:
            notes.append(text)
        end += 1
    return end, heading, notes


def read_class_file(path: Path) -> ClassPage:
    """Terms, dropped lines, and the class heading and notes from one pasted class file."""
    lines = [" ".join(line.replace("\t", " ").split()).strip(" •·-–*;")
             for line in path.read_text(encoding="utf-8-sig", errors="replace").splitlines()]
    lines = [t for t in lines if t]
    top, heading, notes = _top_section(lines)
    kept: list[str] = []
    dropped: list[str] = lines[:top]
    seen: set[str] = set()
    for text in lines[top:]:
        if _is_note(text) and not re.fullmatch(r"class\s*\d{1,2}", text, re.I):
            dropped.append(text)
            if text not in notes:
                notes.append(text)  # a note further down the page
            continue
        if text.isdigit() or len(text) < 2 or len(text) > 2000 or _CHROME.match(text):
            dropped.append(text)
            continue
        if text.lower() not in seen:
            seen.add(text.lower())
            kept.append(text)
    return ClassPage(kept, dropped, heading, notes)


def class_files(folder: Path) -> dict[int, Path]:
    found: dict[int, Path] = {}
    for path in sorted(folder.glob("*.txt")):
        match = _NAME.match(path.stem.strip())
        if match and 1 <= int(match.group(1)) <= 45:
            found[int(match.group(1))] = path
    return found


def import_folder(folder: Path, out: Path = OUT, force: bool = False, log=print) -> PicklistChange:
    files = class_files(Path(folder))
    if not files:
        raise SystemExit(f"No class files found in {folder}. Name them 1.txt to 45.txt (one term per line).")
    existing_items, existing_notes = _existing(out)
    items = [i for i in existing_items if int(i["class_number"]) not in files]
    class_notes = {k: v for k, v in existing_notes.items() if int(k) not in files}
    for class_number, path in sorted(files.items()):
        page = read_class_file(path)
        terms, dropped = page.terms, page.dropped
        if page.heading or page.notes:
            class_notes[str(class_number)] = {"heading": page.heading, "notes": page.notes}
        if not terms:
            raise SystemExit(f"{path.name} has no terms in it. Nothing was changed.")
        items += [{"id": f"{class_number}-{n}", "class_number": class_number, "description": t}
                  for n, t in enumerate(terms, 1)]
        furniture = [d for d in dropped if d != page.heading and d not in page.notes]
        log(f"class {class_number}: {len(terms)} terms"
            + (", heading" if page.heading else "") + (f", {len(page.notes)} notes" if page.notes else "")
            + (f"; left out: {'; '.join(furniture[:6])}" + (" …" if len(furniture) > 6 else "") if furniture else ""))
    missing = sorted(set(range(1, 46)) - {int(i["class_number"]) for i in items})
    if missing:
        log(f"Not imported yet: classes {', '.join(map(str, missing))}")
    items.sort(key=lambda i: int(i["class_number"]))
    return save(items, out, source=SOURCE, force=force,
                extra={"class_notes": dict(sorted(class_notes.items(), key=lambda kv: int(kv[0])))})


def _existing(out: Path) -> tuple[list[dict], dict]:
    try:
        data = json.loads(out.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return [], {}
    if not isinstance(data, dict) or "SAMPLE" in data.get("_note", ""):
        return [], {}
    return data.get("items", []), data.get("class_notes", {})


def main() -> None:
    parser = argparse.ArgumentParser(prog="py -m tm_advisor.picklist_import", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("folder", nargs="?", default=str(ROOT / "data" / "picklist_pages"))
    parser.add_argument("--force", action="store_true", help="replace the list even if the new one is much smaller")
    args = parser.parse_args()
    change = import_folder(Path(args.folder), force=args.force)
    print(f"Saved the picklist to {OUT}. {change.summary()}")


if __name__ == "__main__":
    main()
