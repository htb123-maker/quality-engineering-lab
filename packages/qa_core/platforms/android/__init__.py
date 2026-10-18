"""Android-specific Appium adapters."""

from qa_core.platforms.android.activities import (
    AndroidActivities,
    AndroidActivityTimeout,
    AndroidIntent,
)
from qa_core.platforms.android.clipboard import AndroidClipboard
from qa_core.platforms.android.files import AndroidFiles
from qa_core.platforms.android.gestures import AndroidGestures, ScreenRect, SwipeDirection
from qa_core.platforms.android.hybrid import AndroidWebView, WebViewContextTimeout
from qa_core.platforms.android.permissions import (
    AndroidPermissions,
    PermissionSnapshot,
    PermissionState,
    PermissionStateError,
)

__all__ = [
    "AndroidActivities",
    "AndroidActivityTimeout",
    "AndroidClipboard",
    "AndroidFiles",
    "AndroidGestures",
    "AndroidIntent",
    "AndroidPermissions",
    "AndroidWebView",
    "PermissionSnapshot",
    "PermissionState",
    "PermissionStateError",
    "ScreenRect",
    "SwipeDirection",
    "WebViewContextTimeout",
]
