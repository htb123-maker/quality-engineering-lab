"""Pydantic response contracts shared by the local SUT and API tests."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Role = Literal["owner", "admin", "member", "viewer"]
UserStatus = Literal["active", "disabled"]
CatalogStatus = Literal["active", "archived"]
GrantType = Literal["password", "refresh_token"]


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


class CatalogResponse(ContractModel):
    """Workspace catalog response."""

    workspace: CatalogWorkspace
    items: list[CatalogItem]
    count: int = Field(ge=0)


class ApiError(ContractModel):
    """General API error response."""

    error: str = Field(min_length=1)
    message: str = Field(min_length=1)


class OAuthErrorResponse(ContractModel):
    """OAuth2-compatible error response."""

    error: str = Field(min_length=1)
    error_description: str = Field(min_length=1)
