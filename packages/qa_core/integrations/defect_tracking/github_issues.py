"""Human-approved GitHub Issues adapter for confirmed defects."""

from __future__ import annotations

from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, Field


class GitHubIssueRequest(BaseModel):
    """Reviewed defect content ready for one GitHub issue."""

    model_config = ConfigDict(frozen=True)

    title: str = Field(min_length=1, max_length=240)
    body: str = Field(min_length=1)
    labels: tuple[str, ...] = ()


class GitHubIssueReference(BaseModel):
    """Minimal issue identity returned by GitHub."""

    model_config = ConfigDict(frozen=True)

    number: int = Field(gt=0)
    html_url: str = Field(min_length=1)
    state: str = Field(min_length=1)


class GitHubIssueAdapter:
    """Create a formal issue only after an explicit human approval."""

    def __init__(
        self,
        *,
        token: str,
        repository: str,
        client: httpx.Client | None = None,
    ) -> None:
        if not token.strip():
            raise ValueError("GitHub token must not be empty")
        if repository.count("/") != 1:
            raise ValueError("GitHub repository must be owner/name")
        self._token = token
        self._repository = repository
        self._client = client or httpx.Client(
            base_url="https://api.github.com",
            timeout=20,
        )

    def close(self) -> None:
        self._client.close()

    def create_issue(
        self,
        request: GitHubIssueRequest,
        *,
        approved_by: str,
    ) -> GitHubIssueReference:
        """Create one issue and return its traceable identity."""

        approver = approved_by.strip()
        if not approver:
            raise ValueError("creating a GitHub issue requires a human approver")
        payload: dict[str, Any] = {
            "title": request.title,
            "body": (
                f"Approved by: {approver}\n\n"
                f"{request.body}"
            ),
        }
        if request.labels:
            payload["labels"] = list(request.labels)
        response = self._client.post(
            f"/repos/{self._repository}/issues",
            headers={
                "Authorization": f"Bearer {self._token}",
                "Accept": "application/vnd.github+json",
            },
            json=payload,
        )
        response.raise_for_status()
        return GitHubIssueReference.model_validate(response.json())
