"""Unit tests for the shared document catalog and the GitHub entry pages.

Both scripts live outside the importable ``qa_core`` package, so they are
loaded from their paths. Nothing here uses the network or the real repository:
every tree is built under ``tmp_path``.
"""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path
from typing import Any

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"


def _load_script(name: str) -> Any:
    if str(SCRIPTS_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPTS_DIR))
    spec = importlib.util.spec_from_file_location(name, SCRIPTS_DIR / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


doc_index = _load_script("doc_index")
build_doc_index = _load_script("build_doc_index")


def source(rel_path: str, title: str = "") -> Any:
    return doc_index.SourceDocument(
        rel_path=rel_path,
        slug=doc_index.slug_for(rel_path),
        title=title or rel_path,
        body="",
    )


def write_tree(root: Path, files: dict[str, str]) -> None:
    for rel_path, body in files.items():
        path = root / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")


def link_targets(markdown: str) -> list[str]:
    """Return every link target in document order."""

    return [target for _, target in re.findall(r"\[([^\]]*)\]\(([^)\s]+)\)", markdown)]


@pytest.mark.unit
@pytest.mark.parametrize(
    ("rel_path", "expected"),
    [
        ("docs/GOALS.md", "goals"),
        ("docs/PLAN.md", "plan"),
        (
            "docs/adr/0001-local-sut-with-docker-compose.md",
            "adr-0001-local-sut-with-docker-compose",
        ),
        ("docs/architecture/mobile-driver-call-chain.md", "arch-mobile-driver-call-chain"),
        ("docs/runbooks/local-sut-compose.md", "runbook-local-sut-compose"),
        (
            "docs/test-strategy/defect-lifecycle-and-allure.md",
            "test-strategy-defect-lifecycle-and-allure",
        ),
        ("reports/weekly/WEEK-09.md", "week-09"),
        ("reports/daily/DAY-01.md", "day-01"),
    ],
)
def test_slug_for_maps_repository_paths(rel_path: str, expected: str) -> None:
    assert doc_index.slug_for(rel_path) == expected


@pytest.mark.unit
def test_title_prefers_heading_and_falls_back_to_file_name() -> None:
    assert doc_index.title_for("docs/PLAN.md", "# 项目执行计划\n\n正文") == "项目执行计划"
    assert doc_index.title_for("reports/daily/DAY-01.md", "no heading here") == "DAY 01"


@pytest.mark.unit
def test_long_bilingual_headings_are_shortened_for_entry_pages() -> None:
    heading = (
        "# WEEK-09 - 数据库 Schema、事务、隔离级别、锁与查询计划 / "
        "Database Schema, Transactions, Isolation Levels, Locks, and Query Plans"
    )

    title = doc_index.shorten_title(doc_index.title_for("reports/weekly/WEEK-09.md", heading))

    assert title == "WEEK-09 - 数据库 Schema、事务、隔离级别、锁与查询计划"
    assert len(title) <= doc_index.TITLE_LIMIT


@pytest.mark.unit
def test_discover_documents_skips_templates_index_pages_and_hidden_files(
    tmp_path: Path,
) -> None:
    write_tree(
        tmp_path,
        {
            "docs/PLAN.md": "# 项目执行计划\n",
            "docs/TEMPLATE.md": "# 模板\n",
            "docs/README.md": "# 生成的索引\n",
            "docs/.draft.md": "# 草稿\n",
            "docs/notes.txt": "not markdown\n",
            "reports/weekly/WEEK-09.md": "# WEEK-09\n",
            "reports/README.md": "# 生成的索引\n",
        },
    )

    documents = doc_index.discover_documents(tmp_path, ("docs", "reports"))

    assert [document.rel_path for document in documents] == [
        "docs/PLAN.md",
        "reports/weekly/WEEK-09.md",
    ]
    assert [document.slug for document in documents] == ["plan", "week-09"]


@pytest.mark.unit
def test_ensure_unique_slugs_rejects_collisions() -> None:
    documents = [
        doc_index.SourceDocument("docs/runbook-x.md", "runbook-x", "第一篇", ""),
        doc_index.SourceDocument("docs/runbooks/x.md", "runbook-x", "第二篇", ""),
    ]

    with pytest.raises(ValueError, match="slug collision"):
        doc_index.ensure_unique_slugs(documents)


@pytest.mark.unit
def test_discover_documents_rejects_slug_collisions(tmp_path: Path) -> None:
    write_tree(
        tmp_path,
        {"docs/runbook-x.md": "# 一\n", "docs/runbooks/x.md": "# 二\n"},
    )

    with pytest.raises(ValueError, match="slug collision"):
        doc_index.discover_documents(tmp_path, ("docs",))


@pytest.mark.unit
def test_select_documents_filters_by_name_or_path() -> None:
    documents = [source("docs/PLAN.md"), source("reports/weekly/WEEK-09.md")]

    assert doc_index.select_documents(documents, []) == documents
    assert [d.rel_path for d in doc_index.select_documents(documents, ["WEEK-09.md"])] == [
        "reports/weekly/WEEK-09.md"
    ]
    assert [d.rel_path for d in doc_index.select_documents(documents, ["docs/*"])] == [
        "docs/PLAN.md"
    ]


@pytest.mark.unit
def test_group_for_assigns_canonical_sections() -> None:
    assert doc_index.group_for("docs/PLAN.md") == "目标与计划 / Goals and Plan"
    assert doc_index.group_for("docs/adr/0001-x.md") == "架构决策 / ADR"
    assert doc_index.group_for("reports/daily/DAY-01.md") == "日报 / Daily Reports"
    assert doc_index.group_for("docs/unknown/x.md") == doc_index.OTHER_GROUP


@pytest.mark.unit
def test_grouped_sections_drops_empty_groups() -> None:
    sections = doc_index.grouped_sections([source("docs/PLAN.md")])

    assert [name for name, _ in sections] == ["目标与计划 / Goals and Plan"]


@pytest.mark.unit
def test_report_recency_puts_newest_first_across_kinds() -> None:
    rel_paths = [
        "reports/daily/DAY-01.md",
        "reports/weekly/WEEK-04.md",
        "reports/daily/DAY-07.md",
        "reports/weekly/WEEK-09.md",
    ]

    ordered = sorted(rel_paths, key=doc_index.report_recency, reverse=True)

    assert ordered == [
        "reports/weekly/WEEK-09.md",
        "reports/weekly/WEEK-04.md",
        "reports/daily/DAY-07.md",
        "reports/daily/DAY-01.md",
    ]


@pytest.mark.unit
def test_render_index_lists_titles_and_links() -> None:
    documents = [source("docs/PLAN.md", title="项目执行计划")]

    markdown = doc_index.render_index(
        doc_index.grouped_sections(documents),
        {"docs/PLAN.md": "PLAN.md"},
        title="文档索引",
        notice="> 自动生成",
        intro="共 1 篇",
    )

    assert markdown.startswith("# 文档索引\n\n> 自动生成\n\n共 1 篇\n")
    assert "## 目标与计划 / Goals and Plan" in markdown
    assert "- [项目执行计划](PLAN.md)" in markdown


@pytest.mark.unit
def test_docs_index_links_are_relative_to_the_docs_folder() -> None:
    index = build_doc_index.docs_index(
        [
            source("docs/PLAN.md", title="项目执行计划"),
            source("docs/adr/0001-alpha.md", title="ADR-0001"),
        ]
    )

    assert index.rel_path == "docs/README.md"
    assert link_targets(index.content) == ["PLAN.md", "adr/0001-alpha.md"]


@pytest.mark.unit
def test_reports_index_shows_the_newest_report_first() -> None:
    index = build_doc_index.reports_index(
        [
            source("reports/daily/DAY-01.md", title="DAY-01"),
            source("reports/weekly/WEEK-04.md", title="WEEK-04"),
            source("reports/daily/DAY-07.md", title="DAY-07"),
            source("reports/weekly/WEEK-09.md", title="WEEK-09"),
        ]
    )

    assert index.rel_path == "reports/README.md"
    assert "最新进度：[WEEK-09](weekly/WEEK-09.md)" in index.content
    assert link_targets(index.content) == [
        "weekly/WEEK-09.md",
        "weekly/WEEK-09.md",
        "weekly/WEEK-04.md",
        "daily/DAY-07.md",
        "daily/DAY-01.md",
    ]


def sample_tree(root: Path) -> None:
    write_tree(
        root,
        {
            "docs/PLAN.md": "# 项目执行计划\n",
            "docs/adr/0001-alpha.md": "# ADR-0001: 决策\n",
            "reports/weekly/WEEK-09.md": "# WEEK-09 - 数据库与锁\n",
            "reports/daily/DAY-01.md": "# DAY-01 - 基线\n",
        },
    )


@pytest.mark.unit
def test_build_indexes_reads_a_repository_tree(tmp_path: Path) -> None:
    sample_tree(tmp_path)

    indexes = build_doc_index.build_indexes(tmp_path)

    assert [index.rel_path for index in indexes] == ["docs/README.md", "reports/README.md"]
    assert "- [项目执行计划](PLAN.md)" in indexes[0].content
    assert "- [ADR-0001: 决策](adr/0001-alpha.md)" in indexes[0].content
    assert link_targets(indexes[1].content) == [
        "weekly/WEEK-09.md",
        "weekly/WEEK-09.md",
        "daily/DAY-01.md",
    ]


@pytest.mark.unit
def test_write_indexes_creates_pages_then_reports_them_unchanged(tmp_path: Path) -> None:
    sample_tree(tmp_path)
    indexes = build_doc_index.build_indexes(tmp_path)

    assert build_doc_index.write_indexes(tmp_path, indexes, check=False) == [
        "docs/README.md",
        "reports/README.md",
    ]
    assert (tmp_path / "docs" / "README.md").read_text(encoding="utf-8") == indexes[0].content

    assert build_doc_index.write_indexes(tmp_path, indexes, check=False) == []


@pytest.mark.unit
def test_write_indexes_rebuilds_only_what_changed(tmp_path: Path) -> None:
    sample_tree(tmp_path)
    build_doc_index.write_indexes(tmp_path, build_doc_index.build_indexes(tmp_path), check=False)
    write_tree(tmp_path, {"reports/weekly/WEEK-10.md": "# WEEK-10 - 性能\n"})

    stale = build_doc_index.write_indexes(
        tmp_path,
        build_doc_index.build_indexes(tmp_path),
        check=False,
    )

    assert stale == ["reports/README.md"]


@pytest.mark.unit
def test_write_indexes_check_mode_never_writes(tmp_path: Path) -> None:
    sample_tree(tmp_path)

    stale = build_doc_index.write_indexes(
        tmp_path,
        build_doc_index.build_indexes(tmp_path),
        check=True,
    )

    assert stale == ["docs/README.md", "reports/README.md"]
    assert not (tmp_path / "docs" / "README.md").exists()


@pytest.mark.unit
def test_main_check_fails_on_stale_pages_and_passes_after_writing(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    sample_tree(tmp_path)
    monkeypatch.setattr(build_doc_index, "PROJECT_ROOT", tmp_path)

    assert build_doc_index.main(["--check"]) == 1
    assert "out of date" in capsys.readouterr().err

    assert build_doc_index.main([]) == 0
    assert "updated docs/README.md" in capsys.readouterr().out

    assert build_doc_index.main(["--check"]) == 0
    assert "up to date" in capsys.readouterr().out


@pytest.mark.unit
def test_main_dry_run_prints_without_writing(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    sample_tree(tmp_path)
    monkeypatch.setattr(build_doc_index, "PROJECT_ROOT", tmp_path)

    assert build_doc_index.main(["--dry-run"]) == 0

    assert "--- docs/README.md ---" in capsys.readouterr().out
    assert not (tmp_path / "docs" / "README.md").exists()
