"""iOS-specific Appium framework primitives."""

from qa_core.platforms.ios.devices import (
    IosDeviceMatrix,
    IosDeviceProfile,
    IosWorkerResources,
    allocate_ios_worker_resources,
    build_ios_worker_settings,
    ios_xdist_worker_context,
    load_ios_device_matrix,
    select_ios_worker_device,
)
from qa_core.platforms.ios.diagnostics import (
    IosDiagnostics,
    IosDiagnosticsCapture,
)
from qa_core.platforms.ios.gestures import IosGestures, IosSwipeDirection
from qa_core.platforms.ios.keyboard import IosKeyboard
from qa_core.platforms.ios.locators import IosLocator, IosLocatorStrategy
from qa_core.platforms.ios.permissions import (
    IosAlertAction,
    IosAlertTimeout,
    IosSystemAlerts,
)

__all__ = [
    "IosAlertAction",
    "IosAlertTimeout",
    "IosDeviceMatrix",
    "IosDeviceProfile",
    "IosDiagnostics",
    "IosDiagnosticsCapture",
    "IosGestures",
    "IosKeyboard",
    "IosLocator",
    "IosLocatorStrategy",
    "IosSwipeDirection",
    "IosSystemAlerts",
    "IosWorkerResources",
    "allocate_ios_worker_resources",
    "build_ios_worker_settings",
    "ios_xdist_worker_context",
    "load_ios_device_matrix",
    "select_ios_worker_device",
]
