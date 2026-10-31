"""iOS Screen, explicit wait, gesture, and Flow smoke."""

# mypy: disable-error-code="untyped-decorator,no-untyped-call"

import json
import os
import sys
from typing import Any

import allure
import pytest
from qa_core.config.settings import Settings
from qa_core.driver.ios import create_ios_driver
from qa_core.mobile.flows import Flow, FlowStep
from qa_core.mobile.screens import Screen
from qa_core.platforms.ios import IosGestures, IosLocator, IosSwipeDirection

CLOUD_PROVIDERS = {"browserstack", "saucelabs", "lambdatest"}


class AppWindowScreen(Screen):
    """Stable application-window root shared by Simulator and cloud smoke."""

    root_locator = IosLocator.class_chain(
        "**/XCUIElementTypeWindow[1]",
        "Application window",
    )


def _provider_is_runnable() -> bool:
    provider = os.getenv("QA_IOS_DEVICE_PROVIDER", "local").lower()
    return provider in CLOUD_PROVIDERS or sys.platform == "darwin"


@allure.epic("Quality Engineering Lab")
@allure.feature("iOS Framework")
@allure.story("Screen and flow skeleton")
@pytest.mark.ios
@pytest.mark.smoke
@pytest.mark.skipif(
    not _provider_is_runnable(),
    reason="iOS framework smoke requires macOS or a cloud provider.",
)
@pytest.mark.timeout(900)
@allure.testcase("SMOKE-IOS-FRAMEWORK-001", "iOS screen and gesture framework")
@allure.link(
    "docs/runbooks/ios-locator-wait-keyboard-triage.md",
    name="iOS framework triage",
)
def test_ios_screen_and_gesture_framework(settings: Settings) -> None:
    driver = create_ios_driver(settings)

    try:
        screen = AppWindowScreen(driver).wait_ready()
        gestures = IosGestures(driver)

        def wait_for_window(state: dict[str, Any]) -> dict[str, Any]:
            screen.wait_ready()
            state["window_ready"] = True
            return state

        def swipe_once(state: dict[str, Any]) -> dict[str, Any]:
            gestures.swipe(IosSwipeDirection.UP)
            state["swiped"] = True
            return state

        state = Flow[dict[str, Any]](
            "iOS screen smoke",
            [
                FlowStep("wait for application window", wait_for_window),
                FlowStep("swipe up once", swipe_once),
            ],
        ).run({})

        assert state == {"window_ready": True, "swiped": True}
        window_size = driver.get_window_size()
        assert window_size["width"] > 0
        assert window_size["height"] > 0
        allure.attach(
            json.dumps(window_size, sort_keys=True),
            name="iOS window size",
            attachment_type=allure.attachment_type.JSON,
        )
        allure.attach(
            driver.get_screenshot_as_png(),
            name="iOS framework screenshot",
            attachment_type=allure.attachment_type.PNG,
        )
    finally:
        driver.quit()
