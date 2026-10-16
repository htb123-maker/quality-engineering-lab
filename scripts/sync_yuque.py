"""Publish project documents to Yuque through the official Open API v2.

The Yuque desktop and mobile apps are reading surfaces, not automation
surfaces, so repository documents are pushed from here with a personal access
token that the operator keeps in the git-ignored ``.env`` file. Publishing the
personal token requires a paid Yuque tier; ``scripts/build_doc_index.py``
produces the free GitHub entry pages instead.

Document discovery, slugs, titles and section grouping come from
``doc_index.py`` so both entry pages list the same documents.

Dry run is the default. Pass ``--apply`` to create or update pages.
"""

from __future__ import annotations

import argparse
import json
import os
import posixpath
import re
import sys
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import quote

import httpx
from doc_index import (
    DEFAULT_INCLUDE,
    PROJECT_ROOT,
    SourceDocument,
    configure_console,
    discover_documents,
    grouped_sections,
    render_index,
    select_documents,
)

ENV_FILE = PROJECT_ROOT / ".env"

DEFAULT_API_BASE = "https://www.yuque.com/api/v2"
USER_AGENT = "quality-engineering-lab-yuque-sync/1.0"
DEFAULT_TIMEOUT_SECONDS = 20.0
PAGE_SIZE = 100
MAX_ATTEMPTS = 3
RETRY_STATUS_CODES = frozenset({429, 500, 502, 503, 504})

STATUS_HINTS = {
    401: (
        "the token is wrong or expired. Note that the Yuque Open API is a paid "
        "tier benefit: personal tokens need a Super Member account and team "
        "tokens need a Flagship space."
    ),
    403: (
        "the token cannot write this book. Check YUQUE_NAMESPACE and YUQUE_BOOK, "
        "and confirm the account tier covers Open API access."
    ),
    404: "YUQUE_NAMESPACE or YUQUE_BOOK is wrong, or the token cannot see the book.",
    429: "Yuque rate limited the request; retry later or sync less often.",
}

# Inline links only: the ``(?<!!)`` guard keeps images such as ``![alt](x.png)`` intact.
LINK_PATTERN = re.compile(r"(?<!!)\[([^\]\n]*)\]\(([^)\s]+)\)")

INDEX_SLUG = "index"
INDEX_TITLE = "项目索引 / Project Index"
INDEX_NOTICE = "> 本页由 `scripts/sync_yuque.py` 自动生成，请勿在语雀中手工编辑。"


class ConfigError(RuntimeError):
    """Raised when the Yuque publishing configuration is incomplete."""


class YuqueApiError(RuntimeError):
    """Raised when the Yuque Open API answers with an error status."""

    def __init__(self, status_code: int, message: str) -> None:
        hint = STATUS_HINTS.get(status_code, "")
        detail = f"{message} {hint}".strip() if hint else message
        super().__init__(f"Yuque API returned {status_code}: {detail}")
        self.status_code = status_code
        self.message = message


@dataclass(frozen=True)
class YuqueConfig:
    """Resolved publishing target."""

    token: str
    namespace: str
    book: str
    api_base: str = DEFAULT_API_BASE

    @property
    def book_url(self) -> str:
        return f"https://www.yuque.com/{self.namespace}/{self.book}"


@dataclass(frozen=True)
class SyncOutcome:
    """Result of syncing a single document."""

    rel_path: str
    slug: str
    title: str
    action: str
    url: str


class YuqueApi(Protocol):
    """Minimal Yuque surface needed by the sync loop."""

    def whoami(self) -> Any: ...

    def list_documents(self) -> list[Any]: ...

    def create_document(self, document: SourceDocument) -> Any: ...

    def update_document(self, document_id: str, document: SourceDocument) -> Any: ...


def read_env_file(path: Path) -> dict[str, str]:
    """Read ``KEY=VALUE`` pairs from a dotenv file without touching the real environment."""

    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export ") :].lstrip()
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        if key:
            values[key] = value
    return values


def resolve_config(
    env: Mapping[str, str],
    *,
    require_token: bool,
    require_target: bool = True,
) -> YuqueConfig:
    """Build the publishing target from environment variables.

    ``require_target=False`` supports the book discovery mode, which only needs
    a token because the account itself answers "which knowledge bases exist".
    """

    required: list[tuple[str, bool]] = []
    if require_target:
        required.append(("YUQUE_NAMESPACE", bool(env.get("YUQUE_NAMESPACE", "").strip())))
        required.append(("YUQUE_BOOK", bool(env.get("YUQUE_BOOK", "").strip())))
    if require_token:
        required.append(("YUQUE_TOKEN", bool(env.get("YUQUE_TOKEN", "").strip())))

    missing = [name for name, present in required if not present]
    if missing:
        pronoun = "it" if len(missing) == 1 else "them"
        raise ConfigError(
            "missing "
            + ", ".join(missing)
            + f"; fill {pronoun} in the git-ignored .env at the project root "
            "(see .env.example)."
        )
    return YuqueConfig(
        token=env.get("YUQUE_TOKEN", "").strip(),
        namespace=env.get("YUQUE_NAMESPACE", "").strip(),
        book=env.get("YUQUE_BOOK", "").strip(),
        api_base=(env.get("YUQUE_API_BASE") or DEFAULT_API_BASE).strip(),
    )


def path_segment(value: str) -> str:
    """Percent-encode one URL path segment."""

    return quote(value, safe="")


def document_url(namespace: str, book: str, slug: str) -> str:
    """Build the public Yuque URL of a document."""

    return f"https://www.yuque.com/{namespace}/{book}/{slug}"


def build_url_map(
    documents: Sequence[SourceDocument],
    namespace: str,
    book: str,
) -> dict[str, str]:
    """Map every source path to the Yuque URL it will own."""

    return {
        document.rel_path: document_url(namespace, book, document.slug)
        for document in documents
    }


def rewrite_links(body: str, source_rel_path: str, url_map: Mapping[str, str]) -> str:
    """Point repository-relative Markdown links at their Yuque counterparts."""

    source_dir = posixpath.dirname(source_rel_path)

    def replace(match: re.Match[str]) -> str:
        label, target = match.group(1), match.group(2)
        if target.startswith(("#", "mailto:")) or "://" in target:
            return match.group(0)
        path_part = target.split("#", 1)[0]
        if not path_part:
            return match.group(0)
        if path_part.startswith("/"):
            resolved = path_part.lstrip("/")
        else:
            resolved = posixpath.join(source_dir, path_part) if source_dir else path_part
        url = url_map.get(posixpath.normpath(resolved))
        if url is None:
            return match.group(0)
        # Yuque generates opaque heading anchors, so the link targets the page top.
        return f"[{label}]({url})"

    return LINK_PATTERN.sub(replace, body)


def rewrite_document_links(
    documents: Sequence[SourceDocument],
    url_map: Mapping[str, str],
) -> list[SourceDocument]:
    """Return copies of the documents with cross-document links rewritten."""

    return [
        SourceDocument(
            rel_path=document.rel_path,
            slug=document.slug,
            title=document.title,
            body=rewrite_links(document.body, document.rel_path, url_map),
        )
        for document in documents
    ]


def build_index_document(
    documents: Sequence[SourceDocument],
    url_map: Mapping[str, str],
) -> SourceDocument:
    """Build the generated landing page that makes the hub readable on a phone."""

    body = render_index(
        grouped_sections(documents),
        url_map,
        title=INDEX_TITLE,
        notice=INDEX_NOTICE,
        intro=f"共 {len(documents)} 篇仓库文档，按下方分组跳转。",
    )
    return SourceDocument(
        rel_path=f"<{INDEX_SLUG}>",
        slug=INDEX_SLUG,
        title=INDEX_TITLE,
        body=body,
    )


def build_publish_queue(
    documents: Sequence[SourceDocument],
    *,
    namespace: str,
    book: str,
    include_index: bool,
) -> tuple[list[SourceDocument], dict[str, str]]:
    """Rewrite cross-document links and append the generated index page.

    Returns the ordered queue plus the URL of every queued document, so the CLI
    can print links without talking to the API.
    """

    url_map = build_url_map(documents, namespace, book)
    queue = rewrite_document_links(documents, url_map)
    urls = dict(url_map)
    if include_index:
        index_document = build_index_document(documents, url_map)
        queue.append(index_document)
        urls[index_document.rel_path] = document_url(namespace, book, index_document.slug)
    return queue, urls


def error_message(response: httpx.Response) -> str:
    """Extract a readable message from a Yuque error response."""

    try:
        payload = response.json()
    except ValueError:
        return response.text.strip()[:200] or "unknown error"
    if isinstance(payload, dict):
        message = payload.get("message")
        if isinstance(message, str) and message.strip():
            return message.strip()
    return json.dumps(payload, ensure_ascii=False)[:200]


class YuqueClient:
    """Small Yuque Open API v2 client covering the endpoints this script needs."""

    def __init__(
        self,
        config: YuqueConfig,
        *,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        transport: httpx.BaseTransport | None = None,
        sleep: Any = time.sleep,
    ) -> None:
        self.namespace = config.namespace
        self.book = config.book
        self._sleep = sleep
        self._http = httpx.Client(
            base_url=config.api_base.rstrip("/"),
            timeout=timeout,
            transport=transport,
            headers={
                "X-Auth-Token": config.token,
                "User-Agent": USER_AGENT,
                "Accept": "application/json",
            },
        )

    def __enter__(self) -> YuqueClient:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def close(self) -> None:
        self._http.close()

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        for attempt in range(1, MAX_ATTEMPTS + 1):
            response = self._http.request(method, path, **kwargs)
            if response.status_code in RETRY_STATUS_CODES and attempt < MAX_ATTEMPTS:
                self._sleep(float(2 ** (attempt - 1)))
                continue
            break
        if response.status_code >= 400:
            raise YuqueApiError(response.status_code, error_message(response))
        payload: Any = response.json()
        if isinstance(payload, dict) and "data" in payload:
            return payload["data"]
        return payload

    def whoami(self) -> Any:
        """Return the account that owns the configured token."""

        return self._request("GET", "/user")

    def list_documents(self) -> list[Any]:
        """List every document of the target knowledge base."""

        documents: list[Any] = []
        offset = 0
        while True:
            page = self._request(
                "GET",
                f"/repos/{path_segment(self.namespace)}/{path_segment(self.book)}/docs",
                params={"limit": PAGE_SIZE, "offset": offset},
            )
            if not isinstance(page, list):
                break
            documents.extend(page)
            if len(page) < PAGE_SIZE:
                break
            offset += PAGE_SIZE
        return documents

    def list_books(self, login: str) -> list[Any]:
        """List the knowledge bases this token can see for one account."""

        books: list[Any] = []
        offset = 0
        while True:
            page = self._request(
                "GET",
                f"/users/{path_segment(login)}/repos",
                params={"limit": PAGE_SIZE, "offset": offset},
            )
            if not isinstance(page, list):
                break
            books.extend(page)
            if len(page) < PAGE_SIZE:
                break
            offset += PAGE_SIZE
        return books

    def create_document(self, document: SourceDocument) -> Any:
        """Create a new document and return the API payload."""

        payload = {
            "title": document.title,
            "slug": document.slug,
            "body": document.body,
            "format": "markdown",
        }
        return self._request(
            "POST",
            f"/repos/{path_segment(self.namespace)}/{path_segment(self.book)}/docs",
            json=payload,
        )

    def update_document(self, document_id: str, document: SourceDocument) -> Any:
        """Update an existing document in place, keeping its slug and URL stable."""

        payload = {
            "title": document.title,
            "body": document.body,
            "format": "markdown",
        }
        return self._request(
            "PUT",
            f"/repos/{path_segment(self.namespace)}/{path_segment(self.book)}"
            f"/docs/{path_segment(document_id)}",
            json=payload,
        )


def sync_documents(
    api: YuqueApi,
    documents: Sequence[SourceDocument],
    urls: Mapping[str, str],
    *,
    apply_changes: bool,
) -> list[SyncOutcome]:
    """Create missing documents and update existing ones by slug.

    ``urls`` must cover every queued document; it is built by the caller from
    the same slug rules that the Yuque API applies.
    """

    existing: dict[str, Any] = {}
    if apply_changes:
        for item in api.list_documents():
            if isinstance(item, dict) and item.get("slug"):
                existing.setdefault(str(item["slug"]), item)

    outcomes: list[SyncOutcome] = []
    for document in documents:
        if not apply_changes:
            action = "plan"
        elif document.slug in existing:
            api.update_document(str(existing[document.slug].get("id")), document)
            action = "updated"
        else:
            api.create_document(document)
            action = "created"
        outcomes.append(
            SyncOutcome(
                rel_path=document.rel_path,
                slug=document.slug,
                title=document.title,
                action=action,
                url=urls.get(document.rel_path, ""),
            )
        )
    return outcomes


def print_outcomes(outcomes: Sequence[SyncOutcome], *, applied: bool) -> None:
    """Print a compact table of what happened (or what would happen)."""

    for outcome in outcomes:
        print(f"{outcome.action:<8} {outcome.slug:<34} {outcome.title}")
    prefix = "synced" if applied else "dry run, nothing written"
    counts: dict[str, int] = {}
    for outcome in outcomes:
        counts[outcome.action] = counts.get(outcome.action, 0) + 1
    summary = ", ".join(
        f"{action} {count}" for action, count in sorted(counts.items())
    )
    print(f"\n{prefix}: {summary}")


def planned_outcomes(
    documents: Sequence[SourceDocument],
    urls: Mapping[str, str],
) -> list[SyncOutcome]:
    """Describe a sync that was not executed."""

    return [
        SyncOutcome(
            rel_path=document.rel_path,
            slug=document.slug,
            title=document.title,
            action="plan",
            url=urls.get(document.rel_path, ""),
        )
        for document in documents
    ]


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse command-line options."""

    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="write to Yuque; without it the script only prints the plan",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify the token and the target book, then exit",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="only list the documents and slugs that would be synced",
    )
    parser.add_argument(
        "--books",
        action="store_true",
        help="list the knowledge bases of the token owner (needs only YUQUE_TOKEN)",
    )
    parser.add_argument(
        "--only",
        action="append",
        default=[],
        metavar="GLOB",
        help="sync only matching file names or relative paths; skips the index page",
    )
    parser.add_argument(
        "--include",
        default=",".join(DEFAULT_INCLUDE),
        help="comma separated top-level directories (default: docs,reports)",
    )
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_SECONDS)
    return parser.parse_args(argv)


def run_book_discovery(args: argparse.Namespace) -> int:
    """Print the namespace and book slug of every knowledge base the token sees."""

    env: dict[str, str] = {**read_env_file(ENV_FILE), **os.environ}
    try:
        config = resolve_config(env, require_token=True, require_target=False)
    except ConfigError as error:
        print(f"configuration error: {error}", file=sys.stderr)
        print(
            "--books only needs YUQUE_TOKEN; namespace and book may stay empty here.",
            file=sys.stderr,
        )
        return 2

    try:
        with YuqueClient(config, timeout=args.timeout) as client:
            account = client.whoami()
            if not isinstance(account, dict):
                print("failed: /user returned an unexpected payload.", file=sys.stderr)
                return 1
            login = str(account.get("login") or "")
            if not login:
                print("failed: /user did not return a login.", file=sys.stderr)
                return 1
            print(f"token ok: {account.get('name', '')} ({login})")
            books = client.list_books(login)
    except YuqueApiError as error:
        # The generic status hints talk about namespace and book, which are not
        # set yet in this mode; report the raw status instead.
        print(
            f"failed: Yuque API returned {error.status_code}: {error.message}",
            file=sys.stderr,
        )
        print(
            "fallback: open the knowledge base in a browser and copy the two "
            "path segments of its URL.",
            file=sys.stderr,
        )
        return 1
    except httpx.HTTPError as error:
        print(f"failed: network error {error!r}", file=sys.stderr)
        return 1

    print(f"{'namespace':<20}{'book':<28}name")
    for book in books:
        if not isinstance(book, dict):
            continue
        print(
            f"{str(book.get('namespace', '')):<20}"
            f"{str(book.get('slug', '')):<28}"
            f"{book.get('name', '')}"
        )
    print("")
    print(f"a personal book normally uses your login as namespace: {login}")
    print("copy the namespace and book of the target knowledge base into .env.")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point shared by the CLI and tests."""

    configure_console()
    args = parse_args(argv)
    if args.books:
        return run_book_discovery(args)

    include = tuple(part.strip() for part in args.include.split(",") if part.strip())
    documents = select_documents(discover_documents(PROJECT_ROOT, include), args.only)

    if args.list:
        for document in documents:
            print(f"{document.slug:<38} {document.rel_path}")
        print(f"\n{len(documents)} documents.")
        return 0

    if not documents:
        print("no Markdown documents matched; check --include and --only.", file=sys.stderr)
        return 2

    env: dict[str, str] = {**read_env_file(ENV_FILE), **os.environ}
    try:
        config = resolve_config(env, require_token=args.apply or args.check)
    except ConfigError as error:
        print(f"configuration error: {error}", file=sys.stderr)
        return 2

    queue, urls = build_publish_queue(
        documents,
        namespace=config.namespace,
        book=config.book,
        include_index=not args.only,
    )

    if not (args.apply or args.check):
        print_outcomes(planned_outcomes(queue, urls), applied=False)
        print(f"book: {config.book_url}")
        print("run again with --apply to publish.")
        return 0

    try:
        with YuqueClient(config, timeout=args.timeout) as client:
            if args.check:
                account = client.whoami()
                name = account.get("name") if isinstance(account, dict) else account
                login = account.get("login") if isinstance(account, dict) else ""
                print(f"token ok: {name} ({login})")
                print(f"documents in book: {len(client.list_documents())}")
                print(f"book: {config.book_url}")
                if not args.apply:
                    print("check only, nothing written.")
                    return 0
            outcomes = sync_documents(client, queue, urls, apply_changes=True)
    except YuqueApiError as error:
        print(f"sync failed: {error}", file=sys.stderr)
        return 1
    except httpx.HTTPError as error:
        print(f"sync failed: network error {error!r}", file=sys.stderr)
        return 1

    print_outcomes(outcomes, applied=True)
    print(f"book: {config.book_url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
