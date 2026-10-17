"""Human-reviewable defect drafts derived from reproducible test failures."""

from __future__ import annotations

import importlib
import json
import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from qa_core.reporting.defect_fingerprint import DefectFingerprint


class DefectEvidence(BaseModel):
    """Evidence needed to reproduce and route one failure."""

    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)

    test_id: str = Field(min_length=1)
    pytest_nodeid: str = Field(min_length=1)
    commit: str = Field(default="unknown", min_length=1)
    environment: str = Field(default="local", min_length=1)
    command: str = Field(min_length=1)
    allure_results_path: str | None = None
    ci_run_url: str | None = None
    first_failure: str = Field(min_length=1)


class DefectDraft(BaseModel):
    """A candidate product defect that still requires human triage."""

    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)

    fingerprint: DefectFingerprint
    title: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    expected: str = Field(min_length=1)
    actual: str = Field(min_length=1)
    reproduction_steps: tuple[str, ...] = Field(min_length=1)
    evidence: DefectEvidence
    state: Literal["draft"] = "draft"
    requires_human_approval: Literal[True] = True
    automatically_created_issue: Literal[False] = False

    @property
    def draft_id(self) -> str:
        """Return the stable identifier used by local tracking."""

        return f"DRAFT-{self.fingerprint.digest[:16].upper()}"


def build_defect_draft(
    *,
    fingerprint: DefectFingerprint,
    expected: str,
    actual: str,
    reproduction_steps: tuple[str, ...],
    evidence: DefectEvidence,
) -> DefectDraft:
    """Build a deterministic draft without creating a tracker issue."""

    concise_actual = " ".join(actual.split())
    if len(concise_actual) > 160:
        concise_actual = f"{concise_actual[:157]}..."
    return DefectDraft(
        fingerprint=fingerprint,
        title=f"{evidence.test_id}: {concise_actual}",
        summary=(
            "A test failure produced this draft. Review the evidence and "
            "classify the failure before creating a formal issue."
        ),
        expected=expected,
        actual=actual,
        reproduction_steps=reproduction_steps,
        evidence=evidence,
    )


class JsonlDefectDraftStore:
    """Append-only local draft store that tolerates concurrent xdist writers."""

    def __init__(self, path: Path) -> None:
        self._path = path

    @property
    def path(self) -> Path:
        """Return the JSON Lines file used by this store."""

        return self._path

    def save(self, draft: DefectDraft) -> bool:
        """Persist a draft once; return False when its fingerprint already exists."""

        with self._locked():
            if any(
                existing.fingerprint.digest == draft.fingerprint.digest
                for existing in self.read_all()
            ):
                return False

            line = json.dumps(
                draft.model_dump(mode="json"),
                ensure_ascii=True,
                separators=(",", ":"),
                sort_keys=True,
            )
            payload = f"{line}\n".encode()
            descriptor = os.open(
                self._path,
                os.O_APPEND | os.O_CREAT | os.O_WRONLY,
                0o600,
            )
            try:
                os.write(descriptor, payload)
            finally:
                os.close(descriptor)
            return True

    def read_all(self) -> list[DefectDraft]:
        """Return valid drafts, ignoring malformed lines in an external artifact."""

        if not self._path.exists():
            return []

        drafts: list[DefectDraft] = []
        for line in self._path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                drafts.append(DefectDraft.model_validate_json(line))
            except ValueError:
                continue
        return drafts

    def find_similar(self, draft: DefectDraft) -> list[DefectDraft]:
        """Find exact duplicates, then same-test/signature candidates."""

        all_drafts = self.read_all()
        exact = [
            candidate
            for candidate in all_drafts
            if candidate.fingerprint.digest == draft.fingerprint.digest
        ]
        if exact:
            return exact
        return [
            candidate
            for candidate in all_drafts
            if candidate.fingerprint.test_id == draft.fingerprint.test_id
            and candidate.fingerprint.error_signature
            == draft.fingerprint.error_signature
        ]

    @contextmanager
    def _locked(self) -> Iterator[None]:
        """Serialize append-and-check across threads and xdist processes."""

        self._path.parent.mkdir(parents=True, exist_ok=True)
        lock_path = self._path.with_suffix(f"{self._path.suffix}.lock")
        with lock_path.open("a+b") as lock_file:
            if os.name == "nt":
                msvcrt_api: Any = importlib.import_module("msvcrt")

                lock_file.seek(0)
                msvcrt_api.locking(lock_file.fileno(), msvcrt_api.LK_LOCK, 1)
                try:
                    yield
                finally:
                    lock_file.seek(0)
                    msvcrt_api.locking(lock_file.fileno(), msvcrt_api.LK_UNLCK, 1)
            else:
                fcntl_api: Any = importlib.import_module("fcntl")

                fcntl_api.flock(lock_file.fileno(), fcntl_api.LOCK_EX)
                try:
                    yield
                finally:
                    fcntl_api.flock(lock_file.fileno(), fcntl_api.LOCK_UN)
