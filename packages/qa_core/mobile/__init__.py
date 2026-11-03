"""Typed mobile screen, locator, wait, flow, and cross-platform primitives."""

from qa_core.mobile.diagnostics import MobileDiagnostics, MobileFailureEvidence
from qa_core.mobile.fixture_scenarios import FILE_SCENARIO, NAVIGATION_SCENARIO
from qa_core.mobile.flows import Flow, FlowStep, FlowStepFailure
from qa_core.mobile.locators import Locator, LocatorStrategy
from qa_core.mobile.platforms import (
    LocatorSet,
    MissingLocatorError,
    MobilePlatform,
    NavigationOutcome,
    PlatformAdapter,
    PlatformAdapterRegistry,
    PlatformCapability,
)
from qa_core.mobile.scenarios import (
    MobileScenario,
    ScenarioStep,
    ScenarioStepFailure,
    UnsupportedPlatformError,
)
from qa_core.mobile.screens import Component, Screen
from qa_core.mobile.waits import ElementWaitTimeout, MobileWait, WaitPolicy

__all__ = [
    "Component",
    "ElementWaitTimeout",
    "FILE_SCENARIO",
    "Flow",
    "FlowStep",
    "FlowStepFailure",
    "Locator",
    "LocatorSet",
    "LocatorStrategy",
    "MissingLocatorError",
    "MobileDiagnostics",
    "MobileFailureEvidence",
    "MobilePlatform",
    "MobileScenario",
    "MobileWait",
    "NAVIGATION_SCENARIO",
    "NavigationOutcome",
    "PlatformAdapter",
    "PlatformAdapterRegistry",
    "PlatformCapability",
    "Screen",
    "ScenarioStep",
    "ScenarioStepFailure",
    "UnsupportedPlatformError",
    "WaitPolicy",
]
