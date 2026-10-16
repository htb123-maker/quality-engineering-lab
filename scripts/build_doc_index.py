"""Refresh the GitHub entry pages used when reading this project on a phone.

GitHub renders ``README.md`` automatically when a repository or one of its
folders is opened, and both the mobile app and the mobile web UI render
Markdown and Mermaid blocks. Those two generated pages are therefore the free
reading surface:

- ``docs/README.md``    every design document, grouped
- ``reports/README.md`` every report, newest first

Run it after adding or finishing a report:

    uv run python scripts/build_doc_index.py
    uv run python scripts/build_doc_index.py --check
"""

from __future__ import annotations

import argparse
import posixpath
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from doc_index import (
    PROJECT_ROOT,
    SourceDocument,
    configure_console,
    discover_documents,
    grouped_sections,
    render_index,
    report_recency,
)

DOCS_TITLE = "文档索引 / Documentation Index"
REPORTS_TITLE = "进度索引 / Progress Index"
NOTICE = "> 本页由 `scripts/build_doc_index.py` 自动生成，请勿手工编辑。"


@dataclass(frozen=True)
class IndexFile:
    """One generated entry page."""

    rel_path: str
    content: str


def relative_links(
    documents: Sequence[SourceDocument],
    *,
    base_dir: str,
) -> dict[str, str]:
    """Point every document at its path relative to the index page."""

    return {
        document.rel_path: posixpath.relpath(document.rel_path, base_dir)
        for document in documents
    }


def docs_index(documents: Sequence[SourceDocument]) -> IndexFile:
    """Build ``docs/README.md``."""

    content = render_index(
        grouped_sections(documents),
        relative_links(documents, base_dir="docs"),
        title=DOCS_TITLE,
        notice=NOTICE,
        intro=f"共 {len(documents)} 篇设计文档，按主题分组。",
    )
    return IndexFile(rel_path="docs/README.md", content=content)


def reports_index(documents: Sequence[SourceDocument]) -> IndexFile:
    """Build ``reports/README.md`` with the newest report on top."""

    ordered = sorted(
        documents,
        key=lambda document: report_recency(document.rel_path),
        reverse=True,
    )
    links = relative_links(ordered, base_dir="reports")
    weekly = [document for document in ordered if "/weekly/" in document.rel_path]
    daily = [document for document in ordered if "/daily/" in document.rel_path]
    intro = (
        f"最新进度：[{ordered[0].title}]({links[ordered[0].rel_path]})" if ordered else ""
    )
    content = render_index(
        (("周报 / Weekly Reports", weekly), ("日报 / Daily Reports", daily)),
        links,
        title=REPORTS_TITLE,
        notice=NOTICE,
        intro=intro,
    )
    return IndexFile(rel_path="reports/README.md", content=content)


def build_indexes(root: Path) -> list[IndexFile]:
    """Render both entry pages from the current repository content."""

    return [
        docs_index(discover_documents(root, ("docs",))),
        reports_index(discover_documents(root, ("reports",))),
    ]


def write_indexes(
    root: Path,
    indexes: Sequence[IndexFile],
    *,
    check: bool,
) -> list[str]:
    """Write the pages and return the ones that were stale.

    ``check=True`` only reports; it never writes. Line endings are compared
    through the normal text translation, so a CRLF working copy is not
    reported as stale.
    """

    stale: list[str] = []
    for index in indexes:
        path = root / index.rel_path
        current = path.read_text(encoding="utf-8") if path.is_file() else None
        if current == index.content:
            continue
        stale.append(index.rel_path)
        if not check:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(index.content, encoding="utf-8", newline="\n")
    return stale


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse command-line options."""

    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="exit with 1 when a generated page is out of date; writes nothing",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print the pages instead of writing them",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point shared by the CLI and tests."""

    configure_console()
    args = parse_args(argv)
    indexes = build_indexes(PROJECT_ROOT)

    if args.dry_run:
        for index in indexes:
            print(f"--- {index.rel_path} ---")
            print(index.content)
        return 0

    stale = write_indexes(PROJECT_ROOT, indexes, check=args.check)
    if args.check:
        if stale:
            print("out of date: " + ", ".join(stale), file=sys.stderr)
            print("run: uv run python scripts/build_doc_index.py", file=sys.stderr)
            return 1
        print("entry pages are up to date.")
        return 0

    for index in indexes:
        state = "updated" if index.rel_path in stale else "unchanged"
        print(f"{state} {index.rel_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
