"""iOS-specific Appium framework primitives."""

from qa_core.platforms.ios.adapter import IosFixtureAdapter, IosFixtureFilePort
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
    IosFailureCapture,
    IosFailureClass,
    classify_ios_failure,
)
from qa_core.platforms.ios.gestures import IosGestures, IosSwipeDirection
from qa_core.platforms.ios.inventory import (
    IosAutomationStatus,
    IosTestArea,
    IosTestInventory,
    IosTestPriority,
    IosTestSpec,
    discover_ios_test_node_ids,
    load_ios_test_inventory,
)
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
    "IosAutomationStatus",
    "IosDeviceMatrix",
    "IosDeviceProfile",
    "IosDiagnostics",
    "IosDiagnosticsCapture",
    "IosFailureCapture",
    "IosFailureClass",
    "IosFixtureAdapter",
    "IosFixtureFilePort",
    "IosGestures",
    "IosKeyboard",
    "IosLocator",
    "IosLocatorStrategy",
    "IosSwipeDirection",
    "IosSystemAlerts",
    "IosTestArea",
    "IosTestInventory",
    "IosTestPriority",
    "IosTestSpec",
    "IosWorkerResources",
    "allocate_ios_worker_resources",
    "build_ios_worker_settings",
    "classify_ios_failure",
    "discover_ios_test_node_ids",
    "ios_xdist_worker_context",
    "load_ios_device_matrix",
    "load_ios_test_inventory",
    "select_ios_worker_device",
]
