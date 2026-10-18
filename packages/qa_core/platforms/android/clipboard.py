"""Android clipboard helpers with restoration support."""

from collections.abc import Iterator
from contextlib import contextmanager

from appium.webdriver.webdriver import WebDriver


class AndroidClipboard:
    """Read and write plain text through the UiAutomator2 clipboard API."""

    def __init__(self, driver: WebDriver) -> None:
        self._driver = driver

    def get_text(self) -> str:
        """Return the current plain-text clipboard content."""

        return self._driver.get_clipboard_text()

    def set_text(self, content: str) -> None:
        """Replace the clipboard with plain text."""

        self._driver.set_clipboard_text(content)

    @contextmanager
    def preserve(self) -> Iterator[None]:
        """Restore the previous clipboard value after the context exits."""

        previous = self.get_text()
        try:
            yield
        finally:
            self.set_text(previous)
