"""Android native/WebView context switching."""

from collections.abc import Iterator
from contextlib import contextmanager

from appium.webdriver.webdriver import WebDriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.support.ui import WebDriverWait

from qa_core.mobile.waits import WaitPolicy


class WebViewContextTimeout(TimeoutError):
    """Expected WebView context did not appear before the deadline."""

    def __init__(self, package: str, timeout_seconds: float, available: list[str]) -> None:
        self.package = package
        self.timeout_seconds = timeout_seconds
        self.available = available
        super().__init__(
            f"Timed out after {timeout_seconds:.2f}s waiting for WEBVIEW_{package}; "
            f"available contexts: {available}"
        )


class AndroidWebView:
    """Switch into one package WebView and always return to the prior context."""

    NATIVE_CONTEXT = "NATIVE_APP"

    def __init__(
        self,
        driver: WebDriver,
        policy: WaitPolicy | None = None,
    ) -> None:
        self._driver = driver
        self.policy = policy or WaitPolicy()

    def context_for_package(self, package: str) -> str:
        """Wait for the exact package WebView context."""

        expected = f"WEBVIEW_{package}"
        wait = WebDriverWait(
            self._driver,
            timeout=self.policy.timeout_seconds,
            poll_frequency=self.policy.poll_interval_seconds,
        )
        try:
            return str(
                wait.until(
                    lambda _: expected
                    if expected in self._driver.contexts
                    else False,
                    message=f"waiting for {expected}",
                )
            )
        except TimeoutException as exc:
            raise WebViewContextTimeout(
                package,
                self.policy.timeout_seconds,
                list(self._driver.contexts),
            ) from exc

    @contextmanager
    def activate(self, package: str) -> Iterator[str]:
        """Activate a package WebView and restore the previous context."""

        previous = self._driver.current_context
        target = self.context_for_package(package)
        self._driver.switch_to.context(target)
        try:
            yield target
        finally:
            available = self._driver.contexts
            fallback = previous if previous in available else self.NATIVE_CONTEXT
            self._driver.switch_to.context(fallback)
