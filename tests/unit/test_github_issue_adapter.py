"""Controlled GitHub Issues integration contract."""

import httpx
import pytest
from qa_core.integrations.defect_tracking import (
    GitHubIssueAdapter,
    GitHubIssueRequest,
)


def test_github_issue_requires_human_approval() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(201, json={})

    client = httpx.Client(
        base_url="https://api.github.com",
        transport=httpx.MockTransport(handler),
    )
    adapter = GitHubIssueAdapter(
        token="test-token",
        repository="owner/repo",
        client=client,
    )
    try:
        with pytest.raises(ValueError, match="human approver"):
            adapter.create_issue(
                GitHubIssueRequest(title="Defect", body="Evidence"),
                approved_by=" ",
            )
    finally:
        adapter.close()

    assert requests == []


def test_github_issue_records_approver_and_returns_identity() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["body"] = request.content.decode()
        captured["authorization"] = request.headers["Authorization"]
        return httpx.Response(
            201,
            json={
                "number": 42,
                "html_url": "https://github.com/owner/repo/issues/42",
                "state": "open",
            },
        )

    client = httpx.Client(
        base_url="https://api.github.com",
        transport=httpx.MockTransport(handler),
    )
    adapter = GitHubIssueAdapter(
        token="test-token",
        repository="owner/repo",
        client=client,
    )
    try:
        issue = adapter.create_issue(
            GitHubIssueRequest(
                title="Defect",
                body="Evidence",
                labels=("defect",),
            ),
            approved_by="reviewer",
        )
    finally:
        adapter.close()

    assert issue.number == 42
    assert issue.state == "open"
    assert captured["path"] == "/repos/owner/repo/issues"
    assert captured["authorization"] == "Bearer test-token"
    assert '"Approved by: reviewer' in str(captured["body"])
