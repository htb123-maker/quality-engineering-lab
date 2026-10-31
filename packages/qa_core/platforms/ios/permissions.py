"""Bounded iOS system-alert handling for permission prompts."""

from __future__ import annotations

from enum import StrEnum

from appium.webdriver.webdriver import WebDriver
from selenium.common.exceptions import NoAlertPresentException, TimeoutException
from selenium.webdriver.support.ui import WebDriverWait


class IosAlertTimeout(TimeoutError):
    """Raised when an expected iOS permission alert does not become available."""


class IosAlertAction(StrEnum):
    """Supported permission alert actions."""

    ACCEPT = "accept"
    DISMISS = "dismiss"


class IosSystemAlerts:
    """Accept or dismiss one visible iOS system alert with a deadline."""

    def __init__(self, driver: WebDriver, *, timeout_seconds: float = 10.0) -> None:
        if timeout_seconds <= 0.0:
            raise ValueError("alert timeout must be greater than 0")
        self._driver = driver
        self._timeout_seconds = timeout_seconds

    def _visible_alert(self) -> object:
        try:
            alert = self._driver.switch_to.alert
            _ = alert.text
        except NoAlertPresentException as exc:
            raise LookupError("alert is not present yet") from exc
        return alert

    def wait_until_present(self) -> None:
        """Wait until the Appium alert endpoint returns a visible alert."""

        try:
            WebDriverWait(
                self._driver,
                timeout=self._timeout_seconds,
                poll_frequency=0.25,
                ignored_exceptions=(LookupError,),
            ).until(lambda _: self._visible_alert())
        except TimeoutException as exc:
            raise IosAlertTimeout(
                f"iOS alert did not appear within {self._timeout_seconds:.1f}s"
            ) from exc

    def handle(self, action: IosAlertAction) -> None:
        """Wait for an alert and perform exactly one requested action."""

        if not isinstance(action, IosAlertAction):
            raise TypeError("action must be an IosAlertAction")
        self.wait_until_present()
        alert = self._driver.switch_to.alert
        if action == IosAlertAction.ACCEPT:
            alert.accept()
        else:
            alert.dismiss()
