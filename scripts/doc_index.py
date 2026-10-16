"""Shared catalog rules for the repository's own entry pages.

Two scripts consume this module, so their pages cannot drift apart:

- ``scripts/build_doc_index.py`` renders the GitHub entry pages a phone shows
  first: ``docs/README.md`` and ``reports/README.md``.
- ``scripts/sync_yuque.py`` publishes the same documents to Yuque.

Discovery, slugs, titles and section grouping therefore live here, once.
"""

from __future__ import annotations

import fnmatch
import re
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INCLUDE = ("docs", "reports")
TITLE_LIMIT = 70

# Report templates and generated index pages are structure, not documents.
SKIPPED_FILE_NAMES = frozenset({"TEMPLATE.md", "README.md"})

HEADING_PATTERN = re.compile(r"^#\s+(\S.*)$", re.MULTILINE)
NON_SLUG_CHARACTERS = re.compile(r"[^a-z0-9]+")
REPORT_KIND_LABELS = {"weekly": "week", "daily": "day"}
REPORT_KIND_ORDER = {"weekly": 1, "daily": 0}
DOC_GROUP_LABELS = {
    "adr": "adr",
    "architecture": "arch",
    "runbooks": "runbook",
    "test-strategy": "test-strategy",
}

OTHER_GROUP = "其他 / Other"
INDEX_GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("目标与计划 / Goals and Plan", ("docs/GOALS.md", "docs/PLAN.md")),
    ("架构与结构图 / Architecture", ("docs/architecture/",)),
    ("架构决策 / ADR", ("docs/adr/",)),
    ("测试策略 / Test Strategy", ("docs/test-strategy/",)),
    ("排障手册 / Runbooks", ("docs/runbooks/",)),
    ("周报 / Weekly Reports", ("reports/weekly/",)),
    ("日报 / Daily Reports", ("reports/daily/",)),
)
NUMBER_PATTERN = re.compile(r"^(?:week|day)[-_](\d+)", re.IGNORECASE)


@dataclass(frozen=True)
class SourceDocument:
    """One Markdown file of the project catalog."""

    rel_path: str
    slug: str
    title: str
    body: str


def slugify(text: str) -> str:
    """Return a stable slug: lowercase letters, digits and hyphens."""

    slug = NON_SLUG_CHARACTERS.sub("-", text.lower()).strip("-")
    return slug or "doc"


def slug_for(rel_path: str) -> str:
    """Derive a stable, readable slug from a repository-relative path."""

    parts = Path(rel_path).as_posix().split("/")
    stem = Path(parts[-1]).stem
    directory_parts = parts[1:-1]
    if parts[0] == "docs":
        if not directory_parts:
            return slugify(stem)
        group = DOC_GROUP_LABELS.get(directory_parts[-1], "-".join(directory_parts))
        return slugify(f"{group}-{stem}")
    if parts[0] == "reports" and directory_parts:
        kind = REPORT_KIND_LABELS.get(directory_parts[-1], directory_parts[-1])
        number = re.sub(r"^(?:week|day)[-_]", "", stem, flags=re.IGNORECASE)
        return slugify(f"{kind}-{number}")
    return slugify("-".join(parts))


def shorten_title(title: str, limit: int = TITLE_LIMIT) -> str:
    """Keep entry page titles short while staying faithful to the source heading."""

    if len(title) <= limit:
        return title
    for separator in (" / ", " - "):
        head = title.split(separator, 1)[0].strip()
        if head and len(head) <= limit:
            return head
    return title[: limit - 3].rstrip() + "..."


def title_for(rel_path: str, body: str) -> str:
    """Use the first level-one heading as the title, falling back to the file name."""

    match = HEADING_PATTERN.search(body)
    if match:
        return match.group(1).strip()
    fallback = Path(rel_path).stem.replace("-", " ").replace("_", " ").strip()
    return fallback or rel_path


def discover_documents(root: Path, include: Sequence[str]) -> list[SourceDocument]:
    """Collect Markdown documents below the included top-level directories."""

    documents: list[SourceDocument] = []
    for directory in include:
        base = root / directory
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*.md")):
            if path.name in SKIPPED_FILE_NAMES:
                continue
            relative_parts = path.relative_to(root).parts
            if any(part.startswith(".") for part in relative_parts):
                continue
            rel_path = Path(*relative_parts).as_posix()
            body = path.read_text(encoding="utf-8-sig")
            documents.append(
                SourceDocument(
                    rel_path=rel_path,
                    slug=slug_for(rel_path),
                    title=shorten_title(title_for(rel_path, body)),
                    body=body,
                )
            )
    ensure_unique_slugs(documents)
    return documents


def ensure_unique_slugs(documents: Sequence[SourceDocument]) -> None:
    """Fail loudly instead of silently overwriting a page with a duplicate slug."""

    seen: dict[str, str] = {}
    for document in documents:
        previous = seen.get(document.slug)
        if previous is not None:
            raise ValueError(
                f"slug collision: {previous} and {document.rel_path} both map to "
                f"{document.slug!r}"
            )
        seen[document.slug] = document.rel_path


def select_documents(
    documents: Sequence[SourceDocument],
    patterns: Sequence[str],
) -> list[SourceDocument]:
    """Apply glob filters against the relative path or the file name."""

    if not patterns:
        return list(documents)
    return [
        document
        for document in documents
        if any(
            fnmatch.fnmatch(document.rel_path, pattern)
            or fnmatch.fnmatch(Path(document.rel_path).name, pattern)
            for pattern in patterns
        )
    ]


def group_for(rel_path: str) -> str:
    """Pick the index section a document belongs to."""

    for name, matchers in INDEX_GROUPS:
        for matcher in matchers:
            if matcher.endswith("/"):
                if rel_path.startswith(matcher):
                    return name
            elif rel_path == matcher:
                return name
    return OTHER_GROUP


def grouped_sections(
    documents: Sequence[SourceDocument],
) -> list[tuple[str, list[SourceDocument]]]:
    """Group documents into the canonical index sections, in reading order."""

    grouped: dict[str, list[SourceDocument]] = {}
    for document in documents:
        grouped.setdefault(group_for(document.rel_path), []).append(document)

    order = [name for name, _ in INDEX_GROUPS]
    if OTHER_GROUP in grouped:
        order.append(OTHER_GROUP)
    return [(name, grouped[name]) for name in order if grouped.get(name)]


def report_recency(rel_path: str) -> tuple[int, int]:
    """Sort key that puts the newest report first, weeklies before dailies."""

    parts = Path(rel_path).as_posix().split("/")
    kind = parts[1] if len(parts) > 2 else ""
    match = NUMBER_PATTERN.match(Path(parts[-1]).stem)
    number = int(match.group(1)) if match else 0
    return (REPORT_KIND_ORDER.get(kind, 0), number)


def render_index(
    sections: Sequence[tuple[str, Sequence[SourceDocument]]],
    links: Mapping[str, str],
    *,
    title: str,
    notice: str,
    intro: str = "",
) -> str:
    """Render one index page as Markdown, skipping empty sections."""

    lines = [f"# {title}", ""]
    if notice:
        lines.extend([notice, ""])
    if intro:
        lines.extend([intro, ""])
    for name, documents in sections:
        if not documents:
            continue
        lines.extend([f"## {name}", ""])
        for document in documents:
            lines.append(f"- [{document.title}]({links[document.rel_path]})")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def configure_console() -> None:
    """Keep Chinese document titles from crashing narrow Windows code pages."""

    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(errors="replace")
