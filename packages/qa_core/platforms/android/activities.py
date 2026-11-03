"""Android activity launching and foreground-state waits."""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from appium.webdriver.webdriver import WebDriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.support.ui import WebDriverWait

from qa_core.mobile.waits import WaitPolicy


@dataclass(frozen=True, slots=True)
class AndroidIntent:
    """One explicit Android intent passed to UiAutomator2."""

    action: str
    component: str | None = None
    uri: str | None = None
    package: str | None = None
    categories: tuple[str, ...] = ()
    extras: tuple[tuple[str, str, str], ...] = ()
    flags: str | None = None
    wait: bool = True
    stop: bool = False

    def __post_init__(self) -> None:
        if not self.action.strip():
            raise ValueError("intent action must not be empty")
        if self.component is not None and "/" not in self.component:
            raise ValueError("intent component must use package/activity form")

    def to_payload(self) -> dict[str, object]:
        """Return the argument mapping used by ``mobile: startActivity``."""

        payload: dict[str, object] = {
            "action": self.action,
            "wait": self.wait,
            "stop": self.stop,
        }
        optional_values = {
            "component": self.component,
            "uri": self.uri,
            "package": self.package,
            "flags": self.flags,
        }
        payload.update(
            {
                key: value
                for key, value in optional_values.items()
                if value is not None
            }
        )
        if self.categories:
            payload["categories"] = list(self.categories)
        if self.extras:
            payload["extras"] = [list(item) for item in self.extras]
        return payload


class AndroidActivityTimeout(TimeoutError):
    """Foreground target was not reached before the wait deadline."""

    def __init__(
        self,
        expected: str,
        actual_package: str | None,
        actual_activity: str | None,
        timeout_seconds: float,
    ) -> None:
        self.expected = expected
        self.actual_package = actual_package
        self.actual_activity = actual_activity
        self.timeout_seconds = timeout_seconds
        super().__init__(
            f"Timed out after {timeout_seconds:.2f}s waiting for {expected}; "
            f"currently {actual_package or 'unknown'}/{actual_activity or 'unknown'}"
        )


class AndroidActivities:
    """Launch intents and wait for deterministic package/Activity transitions."""

    START_ACTIVITY_COMMAND = "mobile: startActivity"
    HOME_KEYCODE = 3

    def __init__(
        self,
        driver: WebDriver,
        policy: WaitPolicy | None = None,
    ) -> None:
        self._driver = driver
        self.policy = policy or WaitPolicy()

    def start(self, intent: AndroidIntent) -> None:
        """Start an intent and wait for its explicit component when supplied."""

        self._driver.execute_script(
            self.START_ACTIVITY_COMMAND,
            intent.to_payload(),
        )
        if intent.component is not None:
            self.wait_for_component(intent.component)

    def wait_for_component(
        self,
        component: str,
        policy: WaitPolicy | None = None,
    ) -> tuple[str, str]:
        """Wait until the package/Activity pair is the foreground target."""

        package, activity = component.split("/", 1)
        expected_activity = activity if not activity.startswith(".") else f"{package}{activity}"
        wait = self._wait(policy)
        try:
            result = wait.until(
                lambda _: self._matches_component(package, expected_activity),
                message=f"waiting for {component}",
            )
        except TimeoutException as exc:
            raise AndroidActivityTimeout(
                component,
                self._current_package(),
                self._current_activity(),
                (policy or self.policy).timeout_seconds,
            ) from exc
        return cast(tuple[str, str], result)

    def wait_for_package(
        self,
        package: str,
        policy: WaitPolicy | None = None,
    ) -> str:
        """Wait until any Activity from the package is in the foreground."""

        wait = self._wait(policy)
        try:
            return wait.until(
                lambda _: package if self._current_package() == package else False,
                message=f"waiting for package {package}",
            )
        except TimeoutException as exc:
            raise AndroidActivityTimeout(
                package,
                self._current_package(),
                self._current_activity(),
                (policy or self.policy).timeout_seconds,
            ) from exc

    def wait_for_package_not(
        self,
        package: str,
        policy: WaitPolicy | None = None,
    ) -> str:
        """Wait until the foreground package differs from an excluded package."""

        if not package.strip():
            raise ValueError("excluded package must not be empty")
        wait = self._wait(policy)
        try:
            result = wait.until(
                lambda _: current
                if (current := self._current_package()) and current != package
                else False,
                message=f"waiting to leave package {package}",
            )
        except TimeoutException as exc:
            raise AndroidActivityTimeout(
                f"package other than {package}",
                self._current_package(),
                self._current_activity(),
                (policy or self.policy).timeout_seconds,
            ) from exc
        return result

    def go_home(self) -> None:
        """Send HOME without waiting for a specific launcher implementation."""

        self._driver.press_keycode(self.HOME_KEYCODE)

    def _wait(self, policy: WaitPolicy | None) -> WebDriverWait[WebDriver]:
        effective = policy or self.policy
        return WebDriverWait(
            self._driver,
            timeout=effective.timeout_seconds,
            poll_frequency=effective.poll_interval_seconds,
        )

    def _matches_component(self, package: str, activity: str) -> tuple[str, str] | bool:
        current_package = self._current_package()
        current_activity = self._current_activity()
        if current_package != package or current_activity is None:
            return False
        normalized = (
            current_activity
            if not current_activity.startswith(".")
            else f"{current_package}{current_activity}"
        )
        if normalized != activity:
            return False
        return current_package, current_activity

    def _current_package(self) -> str | None:
        try:
            return self._driver.current_package
        except Exception:
            return None

    def _current_activity(self) -> str | None:
        try:
            return self._driver.current_activity
        except Exception:
            return None
