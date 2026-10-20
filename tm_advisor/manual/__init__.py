"""The Trade Marks Manual of Practice and Procedure: download, parse, chunk and search."""

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

from .index import ManualIndex
from .parse import Chunk, chunk_page, parse_page


def build_index(pages_file: str | Path, index_file: str | Path) -> int:
    """Parse every saved page into chunks and (re)build the search index. Returns the number of chunks."""
    chunks: list[Chunk] = []
    with Path(pages_file).open(encoding="utf-8") as f:
        for line in f:
            page = json.loads(line)
            chunks.extend(chunk_page(parse_page(page["url"], page["html"])))
    index = ManualIndex(index_file)
    index.build(chunks)
    return len(chunks)


def fingerprints(pages_file: str | Path) -> dict[str, str]:
    """URL -> hash of the page's Manual text (not its HTML, so layout tweaks don't count as changes)."""
    result: dict[str, str] = {}
    path = Path(pages_file)
    if not path.exists():
        return result
    with path.open(encoding="utf-8") as f:
        for line in f:
            page = json.loads(line)
            parsed = parse_page(page["url"], page["html"])
            text = "\n".join([parsed.title, parsed.published] + [h for s in parsed.sections for h in [s.heading, *s.text]])
            result[page["url"]] = hashlib.sha256(text.encode()).hexdigest()
    return result


@dataclass
class ManualChange:
    before: int
    after: int
    added: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    changed: list[str] = field(default_factory=list)

    def summary(self) -> str:
        text = (f"{self.after} pages (was {self.before}): {len(self.added)} new, {len(self.removed)} removed, "
                f"{len(self.changed)} changed.")
        for label, urls in (("New", self.added), ("Removed", self.removed), ("Changed", self.changed)):
            for url in urls[:15]:
                text += f"\n  {label}: {url}"
            if len(urls) > 15:
                text += f"\n  … and {len(urls) - 15} more {label.lower()}"
        return text


def compare(old: dict[str, str], new: dict[str, str]) -> ManualChange:
    return ManualChange(before=len(old), after=len(new),
                        added=sorted(new.keys() - old.keys()), removed=sorted(old.keys() - new.keys()),
                        changed=sorted(u for u in new.keys() & old.keys() if new[u] != old[u]))


__all__ = ["Chunk", "ManualChange", "ManualIndex", "build_index", "chunk_page", "compare", "fingerprints", "parse_page"]
