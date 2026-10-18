"""Android permission inspection and deterministic grant/revoke helpers."""

from dataclasses import dataclass
from enum import StrEnum
from typing import cast

from appium.webdriver.webdriver import WebDriver

PERMISSION_PREFIX = "android.permission."


class PermissionState(StrEnum):
    """Observed permission state for one Android permission."""

    GRANTED = "granted"
    DENIED = "denied"
    NOT_REQUESTED = "not_requested"


@dataclass(frozen=True, slots=True)
class PermissionSnapshot:
    """Normalized requested, granted, and denied permissions."""

    package: str
    requested: frozenset[str]
    granted: frozenset[str]
    denied: frozenset[str]

    def state_of(self, permission: str) -> PermissionState:
        """Return the current state of one full Android permission name."""

        if permission in self.granted:
            return PermissionState.GRANTED
        if permission in self.requested:
            return PermissionState.DENIED
        return PermissionState.NOT_REQUESTED


class PermissionStateError(RuntimeError):
    """A permission command completed without producing the requested state."""

    def __init__(self, permission: str, expected: PermissionState, actual: PermissionState) -> None:
        self.permission = permission
        self.expected = expected
        self.actual = actual
        super().__init__(
            f"Permission {permission} expected {expected.value}, observed {actual.value}"
        )


class AndroidPermissions:
    """Read and mutate permissions for one explicit Android package."""

    GET_PERMISSIONS_COMMAND = "mobile: getPermissions"
    CHANGE_PERMISSIONS_COMMAND = "mobile: changePermissions"

    def __init__(self, driver: WebDriver, package: str) -> None:
        if not package.strip():
            raise ValueError("permission package must not be empty")
        self._driver = driver
        self.package = package

    def snapshot(self) -> PermissionSnapshot:
        """Return a normalized snapshot of all permission sets."""

        requested = self._query("requested")
        granted = self._query("granted")
        denied = self._query("denied")
        return PermissionSnapshot(
            package=self.package,
            requested=requested,
            granted=granted,
            denied=denied,
        )

    def grant(self, *permissions: str) -> PermissionSnapshot:
        """Grant requested permissions and verify the resulting state."""

        normalized = self._validate(permissions)
        snapshot = self.snapshot()
        not_requested = normalized.difference(snapshot.requested)
        if not_requested:
            raise ValueError(
                f"Package {self.package} does not request: {sorted(not_requested)}"
            )
        to_grant = tuple(sorted(normalized.difference(snapshot.granted)))
        if to_grant:
            self._change(to_grant, "grant")
        return self._require_state(normalized, PermissionState.GRANTED)

    def revoke(self, *permissions: str) -> PermissionSnapshot:
        """Revoke granted permissions and verify the resulting state."""

        normalized = self._validate(permissions)
        snapshot = self.snapshot()
        not_requested = normalized.difference(snapshot.requested)
        if not_requested:
            raise ValueError(
                f"Package {self.package} does not request: {sorted(not_requested)}"
            )
        to_revoke = tuple(sorted(normalized.intersection(snapshot.granted)))
        if to_revoke:
            self._change(to_revoke, "revoke")
        return self._require_state(normalized, PermissionState.DENIED)

    def _query(self, permission_type: str) -> frozenset[str]:
        values = self._driver.execute_script(
            self.GET_PERMISSIONS_COMMAND,
            {
                "type": permission_type,
                "appPackage": self.package,
            },
        )
        return self._normalize_response(values, permission_type)

    def _change(self, permissions: tuple[str, ...], action: str) -> None:
        self._driver.execute_script(
            self.CHANGE_PERMISSIONS_COMMAND,
            {
                "permissions": list(permissions),
                "appPackage": self.package,
                "action": action,
            },
        )

    def _require_state(
        self,
        permissions: frozenset[str],
        expected: PermissionState,
    ) -> PermissionSnapshot:
        snapshot = self.snapshot()
        for permission in permissions:
            actual = snapshot.state_of(permission)
            if actual is not expected:
                raise PermissionStateError(permission, expected, actual)
        return snapshot

    @staticmethod
    def _normalize_response(values: object, permission_type: str) -> frozenset[str]:
        if not isinstance(values, list) or not all(isinstance(value, str) for value in values):
            raise TypeError(
                f"mobile: getPermissions returned invalid {permission_type} data"
            )
        return frozenset(cast(list[str], values))

    @staticmethod
    def _validate(permissions: tuple[str, ...]) -> frozenset[str]:
        if not permissions:
            raise ValueError("at least one permission is required")
        for permission in permissions:
            if not permission.startswith(PERMISSION_PREFIX):
                raise ValueError(
                    f"Permission must use the full Android name: {permission}"
                )
        return frozenset(permissions)
