"""Unit tests for the Yuque publishing script.

The script lives outside the importable ``qa_core`` package, so it is loaded
from its path. The catalog rules it shares with ``build_doc_index.py`` are
covered by ``test_doc_index.py``; this file covers the Yuque-specific parts. No
test reaches the network: the API client is exercised through
``httpx.MockTransport`` and the sync loop through a fake API object.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import httpx
import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"


def _load_script(name: str) -> Any:
    # Scripts import each other by module name from their own directory.
    if str(SCRIPTS_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPTS_DIR))
    spec = importlib.util.spec_from_file_location(name, SCRIPTS_DIR / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


doc_index = _load_script("doc_index")
sync_yuque = _load_script("sync_yuque")


class FakeYuqueApi:
    """Record writes instead of contacting Yuque."""

    def __init__(self, existing: list[dict[str, Any]] | None = None) -> None:
        self.existing = list(existing or [])
        self.created: list[Any] = []
        self.updated: list[tuple[str, Any]] = []
        self.list_calls = 0

    def whoami(self) -> Any:
        return {"login": "alice", "name": "Alice"}

    def list_documents(self) -> list[Any]:
        self.list_calls += 1
        return list(self.existing)

    def create_document(self, document: Any) -> Any:
        self.created.append(document)
        return {"id": f"new-{len(self.created)}", "slug": document.slug}

    def update_document(self, document_id: str, document: Any) -> Any:
        self.updated.append((document_id, document))
        return {"id": document_id, "slug": document.slug}


class FakeBooksClient:
    """Stand-in for ``YuqueClient`` in the discovery test."""

    def __init__(self, config: Any, **kwargs: Any) -> None:
        self.config = config

    def __enter__(self) -> FakeBooksClient:
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def whoami(self) -> Any:
        return {"login": "alice", "name": "Alice"}

    def list_books(self, login: str) -> list[Any]:
        assert login == "alice"
        return [
            {"namespace": "alice", "slug": "qa-lab", "name": "质量工程平台"},
            {"namespace": "team-x", "slug": "mobile-qa", "name": "Mobile QA"},
        ]


class ExplodingYuqueApi:
    """Fail the test if a dry run decides to touch the API."""

    def whoami(self) -> Any:
        raise AssertionError("dry run must not call the API")

    def list_documents(self) -> list[Any]:
        raise AssertionError("dry run must not call the API")

    def create_document(self, document: Any) -> Any:
        raise AssertionError("dry run must not call the API")

    def update_document(self, document_id: str, document: Any) -> Any:
        raise AssertionError("dry run must not call the API")


def make_document(rel_path: str, body: str = "", title: str = "") -> Any:
    return sync_yuque.SourceDocument(
        rel_path=rel_path,
        slug=doc_index.slug_for(rel_path),
        title=title or rel_path,
        body=body,
    )


def write_tree(root: Path, files: dict[str, str]) -> None:
    for rel_path, body in files.items():
        path = root / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")


@pytest.mark.unit
def test_rewrite_links_points_relative_markdown_at_yuque() -> None:
    url_map = {
        "docs/GOALS.md": "https://www.yuque.com/alice/qa-lab/goals",
        "reports/weekly/WEEK-09.md": "https://www.yuque.com/alice/qa-lab/week-09",
    }
    body = (
        "[目标](GOALS.md)\n"
        "[周报](../reports/weekly/WEEK-09.md)\n"
        "[带锚点](GOALS.md#section)\n"
        "[缺失](missing.md)\n"
        "[外链](https://example.com/a.md)\n"
        "![截图](shot.png)\n"
        "[页内](#section)\n"
    )

    rewritten = sync_yuque.rewrite_links(body, "docs/PLAN.md", url_map)

    assert "[目标](https://www.yuque.com/alice/qa-lab/goals)" in rewritten
    assert "[周报](https://www.yuque.com/alice/qa-lab/week-09)" in rewritten
    assert "[带锚点](https://www.yuque.com/alice/qa-lab/goals)" in rewritten
    assert "[缺失](missing.md)" in rewritten
    assert "[外链](https://example.com/a.md)" in rewritten
    assert "![截图](shot.png)" in rewritten
    assert "[页内](#section)" in rewritten


@pytest.mark.unit
def test_publish_queue_appends_the_generated_index_page() -> None:
    documents = [
        make_document("docs/PLAN.md", "# 项目执行计划\n\n见 [目标](GOALS.md)。", "项目执行计划"),
        make_document("docs/GOALS.md", "# 项目目标文档\n", "项目目标文档"),
    ]

    queue, urls = sync_yuque.build_publish_queue(
        documents,
        namespace="alice",
        book="qa-lab",
        include_index=True,
    )

    assert [document.slug for document in queue] == ["plan", "goals", "index"]
    assert "[目标](https://www.yuque.com/alice/qa-lab/goals)" in queue[0].body
    index = queue[-1]
    assert index.title == sync_yuque.INDEX_TITLE
    assert sync_yuque.INDEX_NOTICE in index.body
    assert "- [项目执行计划](https://www.yuque.com/alice/qa-lab/plan)" in index.body
    assert "- [项目目标文档](https://www.yuque.com/alice/qa-lab/goals)" in index.body
    assert urls["<index>"] == "https://www.yuque.com/alice/qa-lab/index"


@pytest.mark.unit
def test_publish_queue_without_index_keeps_filtered_runs_away_from_the_index() -> None:
    documents = [make_document("reports/weekly/WEEK-09.md", "# WEEK-09\n")]

    queue, urls = sync_yuque.build_publish_queue(
        documents,
        namespace="alice",
        book="qa-lab",
        include_index=False,
    )

    assert [document.slug for document in queue] == ["week-09"]
    assert sync_yuque.INDEX_SLUG not in {document.slug for document in queue}
    assert "<index>" not in urls


@pytest.mark.unit
def test_dry_run_reports_a_plan_without_calling_the_api() -> None:
    documents = [make_document("docs/PLAN.md"), make_document("docs/GOALS.md")]

    outcomes = sync_yuque.sync_documents(
        ExplodingYuqueApi(),
        documents,
        {"docs/PLAN.md": "https://www.yuque.com/alice/qa-lab/plan"},
        apply_changes=False,
    )

    assert [outcome.action for outcome in outcomes] == ["plan", "plan"]
    assert outcomes[0].url == "https://www.yuque.com/alice/qa-lab/plan"
    assert outcomes[1].url == ""


@pytest.mark.unit
def test_apply_creates_missing_documents_and_updates_existing_ones() -> None:
    api = FakeYuqueApi(existing=[{"id": 42, "slug": "plan"}])
    documents = [
        make_document("docs/PLAN.md", "# 项目执行计划\n"),
        make_document("docs/GOALS.md", "# 项目目标文档\n"),
    ]

    outcomes = sync_yuque.sync_documents(
        api,
        documents,
        {},
        apply_changes=True,
    )

    assert [outcome.action for outcome in outcomes] == ["updated", "created"]
    assert [document.slug for document in api.created] == ["goals"]
    assert api.updated[0][0] == "42"
    assert api.updated[0][1].slug == "plan"
    assert api.list_calls == 1


@pytest.mark.unit
def test_resolve_config_requires_namespace_and_book_even_for_dry_runs() -> None:
    with pytest.raises(sync_yuque.ConfigError, match="YUQUE_NAMESPACE"):
        sync_yuque.resolve_config({}, require_token=False)

    config = sync_yuque.resolve_config(
        {"YUQUE_NAMESPACE": "alice", "YUQUE_BOOK": "qa-lab"},
        require_token=False,
    )

    assert config.token == ""
    assert config.book_url == "https://www.yuque.com/alice/qa-lab"


@pytest.mark.unit
def test_resolve_config_requires_a_token_before_writing() -> None:
    env = {"YUQUE_NAMESPACE": "alice", "YUQUE_BOOK": "qa-lab"}

    with pytest.raises(sync_yuque.ConfigError, match="YUQUE_TOKEN"):
        sync_yuque.resolve_config(env, require_token=True)


@pytest.mark.unit
def test_resolve_config_supports_token_only_book_discovery() -> None:
    config = sync_yuque.resolve_config(
        {"YUQUE_TOKEN": "token-123"},
        require_token=True,
        require_target=False,
    )

    assert config.token == "token-123"
    assert config.namespace == ""
    assert config.book == ""


@pytest.mark.unit
def test_books_mode_prints_namespace_and_book_of_every_knowledge_base(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(sync_yuque, "ENV_FILE", tmp_path / "missing.env")
    monkeypatch.setenv("YUQUE_TOKEN", "token-123")
    monkeypatch.setattr(sync_yuque, "YuqueClient", FakeBooksClient)

    assert sync_yuque.main(["--books"]) == 0

    output = capsys.readouterr().out
    assert "token ok: Alice (alice)" in output
    assert "qa-lab" in output
    assert "mobile-qa" in output
    assert "namespace" in output


@pytest.mark.unit
def test_books_mode_requires_a_token(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(sync_yuque, "ENV_FILE", tmp_path / "missing.env")
    monkeypatch.delenv("YUQUE_TOKEN", raising=False)

    assert sync_yuque.main(["--books"]) == 2
    assert "YUQUE_TOKEN" in capsys.readouterr().err


@pytest.mark.unit
def test_read_env_file_parses_dotenv_syntax(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "# comment\nYUQUE_NAMESPACE=alice\n\nexport YUQUE_BOOK='qa-lab'\n",
        encoding="utf-8",
    )

    values = sync_yuque.read_env_file(env_file)

    assert values == {"YUQUE_NAMESPACE": "alice", "YUQUE_BOOK": "qa-lab"}


def make_client(handler: Any, sleep: Any = None) -> Any:
    config = sync_yuque.YuqueConfig(token="token-123", namespace="alice", book="qa-lab")
    return sync_yuque.YuqueClient(
        config,
        transport=httpx.MockTransport(handler),
        sleep=sleep or (lambda _seconds: None),
    )


@pytest.mark.unit
def test_client_sends_auth_header_user_agent_and_base_path() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"data": {"login": "alice", "name": "Alice"}})

    with make_client(handler) as client:
        account = client.whoami()

    assert account == {"login": "alice", "name": "Alice"}
    assert seen[0].url == "https://www.yuque.com/api/v2/user"
    assert seen[0].headers["X-Auth-Token"] == "token-123"
    assert seen[0].headers["User-Agent"] == sync_yuque.USER_AGENT


@pytest.mark.unit
def test_client_creates_documents_with_markdown_format() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"data": {"id": 7, "slug": "plan"}})

    document = sync_yuque.SourceDocument(
        rel_path="docs/PLAN.md",
        slug="plan",
        title="项目执行计划",
        body="# 项目执行计划\n",
    )

    with make_client(handler) as client:
        client.create_document(document)

    request = seen[0]
    assert request.method == "POST"
    assert request.url == "https://www.yuque.com/api/v2/repos/alice/qa-lab/docs"
    assert json.loads(request.content) == {
        "title": "项目执行计划",
        "slug": "plan",
        "body": "# 项目执行计划\n",
        "format": "markdown",
    }


@pytest.mark.unit
def test_client_updates_documents_by_id() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"data": {"id": 7, "slug": "plan"}})

    document = sync_yuque.SourceDocument(
        rel_path="docs/PLAN.md",
        slug="plan",
        title="项目执行计划",
        body="# 项目执行计划\n",
    )

    with make_client(handler) as client:
        client.update_document("7", document)

    request = seen[0]
    assert request.method == "PUT"
    assert request.url == "https://www.yuque.com/api/v2/repos/alice/qa-lab/docs/7"
    payload = json.loads(request.content)
    assert payload["title"] == "项目执行计划"
    assert "slug" not in payload


@pytest.mark.unit
def test_client_raises_a_hint_for_unauthorized_responses() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"status": 401, "message": "Unauthorized"})

    with make_client(handler) as client, pytest.raises(sync_yuque.YuqueApiError) as error:
        client.list_documents()

    assert error.value.status_code == 401
    assert "Super Member" in str(error.value)


@pytest.mark.unit
def test_client_retries_rate_limited_requests() -> None:
    responses = [
        httpx.Response(429, json={"status": 429, "message": "Too Many Requests"}),
        httpx.Response(200, json={"data": {"login": "alice"}}),
    ]
    sleeps: list[float] = []

    def handler(_request: httpx.Request) -> httpx.Response:
        return responses.pop(0)

    with make_client(handler, sleep=sleeps.append) as client:
        assert client.whoami() == {"login": "alice"}

    assert sleeps == [1.0]
    assert responses == []


@pytest.mark.unit
def test_client_paginates_document_lists() -> None:
    pages = {
        0: [{"slug": f"doc-{index}"} for index in range(sync_yuque.PAGE_SIZE)],
        100: [{"slug": "last-doc"}],
    }
    offsets: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        offset = int(request.url.params["offset"])
        offsets.append(offset)
        return httpx.Response(200, json={"data": pages[offset]})

    with make_client(handler) as client:
        documents = client.list_documents()

    assert offsets == [0, 100]
    assert len(documents) == sync_yuque.PAGE_SIZE + 1
    assert documents[-1]["slug"] == "last-doc"


@pytest.mark.unit
def test_client_lists_books_for_an_account() -> None:
    seen: list[httpx.Request] = []
    payload = [{"namespace": "alice", "slug": "qa-lab", "name": "质量工程平台"}]

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"data": payload})

    with make_client(handler) as client:
        books = client.list_books("alice")

    assert books == payload
    assert seen[0].url.path == "/api/v2/users/alice/repos"
    assert seen[0].url.params["limit"] == str(sync_yuque.PAGE_SIZE)
    assert seen[0].headers["X-Auth-Token"] == "token-123"
