"""Android remote file operations for device-side test evidence."""

import base64
from pathlib import PurePosixPath
from uuid import uuid4

from appium.webdriver.webdriver import WebDriver
from selenium.common.exceptions import WebDriverException


class AndroidFiles:
    """Push, read, and delete UTF-8 files on an Android device."""

    DELETE_FILE_COMMAND = "mobile: deleteFile"

    def __init__(self, driver: WebDriver) -> None:
        self._driver = driver

    def write_text(self, remote_path: str, content: str) -> None:
        """Push UTF-8 text to an absolute device path."""

        self._validate_path(remote_path)
        encoded = base64.b64encode(content.encode("utf-8")).decode("ascii")
        self._driver.push_file(remote_path, encoded)

    def read_text(self, remote_path: str) -> str:
        """Pull and decode UTF-8 text from an absolute device path."""

        self._validate_path(remote_path)
        return base64.b64decode(self._driver.pull_file(remote_path)).decode("utf-8")

    def delete(self, remote_path: str) -> None:
        """Delete a file or folder from the device."""

        self._validate_path(remote_path)
        self._driver.execute_script(
            self.DELETE_FILE_COMMAND,
            {"remotePath": remote_path},
        )

    def exists(self, remote_path: str) -> bool:
        """Return whether the path can currently be pulled."""

        self._validate_path(remote_path)
        try:
            self._driver.pull_file(remote_path)
        except WebDriverException:
            return False
        return True

    @staticmethod
    def temporary_path(directory: str = "/sdcard/Download") -> str:
        """Create a unique test path without creating the file."""

        AndroidFiles._validate_path(directory)
        return str(PurePosixPath(directory) / f"qa-week15-{uuid4().hex}.txt")

    @staticmethod
    def _validate_path(remote_path: str) -> None:
        path = PurePosixPath(remote_path)
        if not path.is_absolute():
            raise ValueError("Android file path must be absolute")
        if ".." in path.parts:
            raise ValueError("Android file path must not contain '..'")
