"""The Trade Marks Manual of Practice and Procedure: download, parse, chunk and search."""

import json
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


__all__ = ["Chunk", "ManualIndex", "build_index", "chunk_page", "parse_page"]
