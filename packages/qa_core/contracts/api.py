"""Pydantic response contracts shared by the local SUT and API tests."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

Role = Literal["owner", "admin", "member", "viewer"]
UserStatus = Literal["active", "disabled"]
CatalogStatus = Literal["active", "archived"]
GrantType = Literal["password", "refresh_token"]
JobStatus = Literal["queued", "running", "succeeded", "failed"]
SkuPattern = r"^[A-Z0-9][A-Z0-9-]*$"
Capability = Literal[
    "audit:read",
    "catalog:read",
    "catalog:refresh",
    "catalog:write",
    "events:read",
    "jobs:read",
    "members:read",
    "members:write",
]

# Only these roles may be handed out through the members API. ``owner`` is
# deliberately absent: ownership transfer is not an API operation, so a request
# can never escalate itself or a peer straight to owner.
AssignableRole = Literal["admin", "member", "viewer"]
MemberEmailPattern = r"^[^@\s]+@[^@\s.]+(\.[^@\s.]+)+$"


class ContractModel(BaseModel):
    """Base model that treats the documented response shape as exact."""

    model_config = ConfigDict(extra="forbid")


class RootResponse(ContractModel):
    """Service metadata returned by the root route."""

    service: Literal["quality-engineering-lab-sut"]
    status: Literal["ok"]
    endpoints: list[str]


class HealthLiveResponse(ContractModel):
    """Liveness response."""

    status: Literal["live"]


class HealthCheck(ContractModel):
    """One dependency check in the readiness response."""

    status: Literal["ok", "error"]
    database: str | None = None
    user: str | None = None
    ping: bool | None = None
    error: str | None = None


class ReadinessResponse(ContractModel):
    """Readiness response containing dependency checks."""

    status: Literal["ready", "degraded"]
    checks: dict[str, HealthCheck]


class OidcMetadataResponse(ContractModel):
    """OpenID Connect discovery metadata exposed by the local SUT."""

    issuer: str = Field(min_length=1)
    token_endpoint: str = Field(pattern=r"^/")
    userinfo_endpoint: str = Field(pattern=r"^/")
    revocation_endpoint: str = Field(pattern=r"^/")
    grant_types_supported: list[GrantType]


class TokenResponse(ContractModel):
    """OAuth2 token endpoint response."""

    access_token: str = Field(min_length=1)
    refresh_token: str = Field(min_length=1)
    token_type: Literal["Bearer"]
    expires_in: int = Field(gt=0)
    scope: Literal["openid profile"]


class UserResponse(ContractModel):
    """Authenticated user representation."""

    id: int = Field(gt=0)
    workspace_id: int = Field(gt=0)
    workspace_slug: str = Field(min_length=1)
    email: str = Field(min_length=3)
    display_name: str = Field(min_length=1)
    role: Role
    status: UserStatus


class AdminAuditResponse(ContractModel):
    """Owner/admin-only audit summary."""

    workspace_slug: str = Field(min_length=1)
    role: Literal["owner", "admin"]
    events: list[str]


class PermissionsResponse(ContractModel):
    """The authenticated caller's role and the capabilities it unlocks."""

    user_id: int = Field(gt=0)
    workspace_slug: str = Field(min_length=1)
    role: Role
    capabilities: list[Capability]


class MemberResponse(ContractModel):
    """One workspace member row."""

    id: int = Field(gt=0)
    workspace_id: int = Field(gt=0)
    email: str = Field(min_length=3, max_length=254)
    display_name: str = Field(min_length=1, max_length=80)
    role: Role
    status: UserStatus


class MembersResponse(ContractModel):
    """The member list of one workspace."""

    workspace_slug: str = Field(min_length=1)
    count: int = Field(ge=0)
    members: list[MemberResponse]


class MemberCreate(ContractModel):
    """Request body that invites one member into a workspace."""

    email: str = Field(min_length=5, max_length=254, pattern=MemberEmailPattern)
    display_name: str = Field(min_length=1, max_length=80)
    role: AssignableRole


class MemberRoleUpdate(ContractModel):
    """Request body that changes one member's role."""

    role: AssignableRole


class RevokeResponse(ContractModel):
    """OAuth2 revocation response."""

    revoked: bool


class CatalogWorkspace(ContractModel):
    """Workspace summary embedded in a catalog response."""

    slug: str = Field(min_length=1)
    name: str = Field(min_length=1)


class CatalogItem(ContractModel):
    """One catalog item."""

    id: int = Field(gt=0)
    sku: str = Field(min_length=1)
    name: str = Field(min_length=1)
    price_cents: int = Field(ge=0)
    status: CatalogStatus


class CatalogItemCreate(ContractModel):
    """Request body for creating one catalog item."""

    sku: str = Field(min_length=3, max_length=64, pattern=SkuPattern)
    name: str = Field(min_length=1, max_length=120)
    price_cents: int = Field(ge=0, le=100_000_000)

    @field_validator("name")
    @classmethod
    def _reject_control_characters(cls, value: str) -> str:
        """Store text, not terminal or protocol control sequences."""

        if any(ord(character) < 32 or ord(character) == 127 for character in value):
            raise ValueError("name must not contain control characters")
        return value


class CatalogItemStatusUpdate(ContractModel):
    """Request body for a catalog item state transition."""

    status: CatalogStatus


class CatalogResponse(ContractModel):
    """Workspace catalog response."""

    workspace: CatalogWorkspace
    items: list[CatalogItem]
    count: int = Field(ge=0)


class CacheRefreshRequest(ContractModel):
    """Request body for an asynchronous catalog cache refresh."""

    delay_seconds: float = Field(default=0.0, ge=0.0, le=30.0)
    ttl_seconds: int | None = Field(default=None, ge=1, le=3600)


class JobAcceptedResponse(ContractModel):
    """202 response returned when a background job is queued."""

    job_id: str = Field(min_length=1)
    type: str = Field(min_length=1)
    workspace_slug: str = Field(min_length=1)
    status: Literal["queued"]
    queued_at: str = Field(min_length=1)


class JobResponse(ContractModel):
    """One background job record."""

    job_id: str = Field(min_length=1)
    type: str = Field(min_length=1)
    workspace_slug: str = Field(min_length=1)
    status: JobStatus
    queued_at: str = Field(min_length=1)
    started_at: str | None = None
    finished_at: str | None = None
    result: dict[str, Any] | None = None
    error: str | None = None


class JobQueueStatsResponse(ContractModel):
    """Queue depth and worker counters used as asynchronous evidence."""

    queued: int = Field(ge=0)
    delayed: int = Field(ge=0)
    processed: int = Field(ge=0)
    failed: int = Field(ge=0)
    worker_enabled: bool


class CatalogEvent(ContractModel):
    """One pushed workspace event, as delivered on the WebSocket stream."""

    type: str = Field(min_length=1)
    workspace: str = Field(min_length=1)
    sequence: int = Field(ge=1)
    occurred_at: float = Field(gt=0)
    data: dict[str, Any]


class FieldError(ContractModel):
    """One field-level validation failure in a request body."""

    field: str = Field(min_length=1)
    message: str = Field(min_length=1)
    type: str = Field(min_length=1)


class ValidationErrorResponse(ContractModel):
    """422 response describing which request fields were rejected."""

    error: Literal["validation_failed"]
    message: str = Field(min_length=1)
    fields: list[FieldError]


class ApiError(ContractModel):
    """General API error response."""

    error: str = Field(min_length=1)
    message: str = Field(min_length=1)


class OAuthErrorResponse(ContractModel):
    """OAuth2-compatible error response."""

    error: str = Field(min_length=1)
    error_description: str = Field(min_length=1)
