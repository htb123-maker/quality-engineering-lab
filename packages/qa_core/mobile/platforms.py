"""Cross-platform adapter and semantic-locator contracts."""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import TYPE_CHECKING, Protocol

from qa_core.mobile.locators import LocatorLike

if TYPE_CHECKING:
    from qa_core.mobile.diagnostics import MobileFailureEvidence

_LOCATOR_KEY = re.compile(r"^[a-z][a-z0-9_.-]*$")


class MobilePlatform(StrEnum):
    """Platforms supported by the shared mobile scenario layer."""

    ANDROID = "android"
    IOS = "ios"


class PlatformCapability(StrEnum):
    """Capabilities a platform adapter can expose to business flows."""

    NAVIGATION = "navigation"
    FILES = "files"
    DIAGNOSTICS = "diagnostics"


class NavigationOutcome(StrEnum):
    """Normalized result of one fixture navigation action."""

    COMPLETED = "completed"


class MissingLocatorError(KeyError):
    """A semantic locator key is absent from one platform adapter."""

    def __init__(
        self,
        platform: MobilePlatform,
        key: str,
        available: tuple[str, ...],
    ) -> None:
        self.platform = platform
        self.key = key
        self.available = available
        available_text = ", ".join(available) or "<none>"
        super().__init__(
            f"{platform.value} locator set is missing {key!r}; "
            f"available keys: {available_text}"
        )


@dataclass(frozen=True, slots=True)
class LocatorSet:
    """Platform locators indexed by platform-neutral semantic keys."""

    platform: MobilePlatform
    entries: Mapping[str, LocatorLike]

    def __post_init__(self) -> None:
        if not isinstance(self.platform, MobilePlatform):
            raise TypeError("platform must be a MobilePlatform")
        if not self.entries:
            raise ValueError("locator set must contain at least one entry")
        copied: dict[str, LocatorLike] = {}
        for key, locator in self.entries.items():
            if not isinstance(key, str) or not _LOCATOR_KEY.fullmatch(key):
                raise ValueError(
                    "locator key must start with a lowercase letter and use "
                    "lowercase letters, digits, dots, underscores, or hyphens"
                )
            if not callable(getattr(locator, "as_tuple", None)):
                raise TypeError(f"locator for {key!r} must provide as_tuple()")
            copied[key] = locator
        object.__setattr__(self, "entries", MappingProxyType(copied))

    def get(self, key: str) -> LocatorLike:
        """Return one locator or fail with a platform-aware contract error."""

        try:
            return self.entries[key]
        except KeyError as exc:
            raise MissingLocatorError(
                self.platform,
                key,
                tuple(sorted(self.entries)),
            ) from exc

    def require(self, *keys: str) -> None:
        """Validate that all required semantic keys are present."""

        missing = tuple(key for key in keys if key not in self.entries)
        if missing:
            raise MissingLocatorError(
                self.platform,
                ", ".join(missing),
                tuple(sorted(self.entries)),
            )

    def __len__(self) -> int:
        return len(self.entries)

    def __contains__(self, key: object) -> bool:
        return key in self.entries


class FilePort(Protocol):
    """Business-level file write/read/cleanup contract."""

    def write_text(self, content: str) -> None:
        """Persist one text payload for the current fixture session."""

    def read_text(self) -> str:
        """Read the payload written by the latest write operation."""

    def cleanup(self) -> None:
        """Delete temporary state without failing if it is already absent."""


class PlatformAdapter(Protocol):
    """Platform-specific implementation consumed by shared business scenarios."""

    @property
    def platform(self) -> MobilePlatform:
        """Return the adapter platform."""

    @property
    def capabilities(self) -> frozenset[PlatformCapability]:
        """Return enabled business-level capabilities."""

    @property
    def locators(self) -> LocatorSet:
        """Return the semantic locator set."""

    @property
    def files(self) -> FilePort:
        """Return the fixture file interaction port."""

    def launch_fixture(self) -> None:
        """Launch or reset the fixture to a deterministic root state."""

    def tap(self, locator_key: str) -> None:
        """Tap one semantic locator."""

    def text(self, locator_key: str) -> str:
        """Read text from one semantic locator."""

    def trigger_navigation(self) -> NavigationOutcome:
        """Trigger fixture navigation and verify its observable result."""

    def capture_failure(
        self,
        *,
        scenario_id: str,
        step_id: str,
        error: BaseException,
        context: Mapping[str, object] | None = None,
    ) -> MobileFailureEvidence | None:
        """Persist failure evidence when a diagnostics directory is configured."""


AdapterFactory = Callable[..., PlatformAdapter]


class PlatformAdapterRegistry:
    """Factory registry; the only layer allowed to select a platform adapter."""

    def __init__(self) -> None:
        self._factories: dict[MobilePlatform, AdapterFactory] = {}

    def register(
        self,
        platform: MobilePlatform,
        factory: AdapterFactory,
        *,
        replace: bool = False,
    ) -> None:
        """Register one adapter factory without silent replacements."""

        if not isinstance(platform, MobilePlatform):
            raise TypeError("platform must be a MobilePlatform")
        if not callable(factory):
            raise TypeError("factory must be callable")
        if platform in self._factories and not replace:
            raise ValueError(f"adapter factory already registered for {platform.value}")
        self._factories[platform] = factory

    def create(self, platform: MobilePlatform, **kwargs: object) -> PlatformAdapter:
        """Create an adapter for an explicit platform."""

        try:
            factory = self._factories[platform]
        except KeyError as exc:
            raise LookupError(
                f"no adapter factory registered for {platform.value}"
            ) from exc
        return factory(**kwargs)
