"""Static contract tests for the Week 19 iOS fixture project."""

from __future__ import annotations

import plistlib
from pathlib import Path
from xml.etree import ElementTree

FIXTURE_ROOT = Path("apps/ios-fixture")
APP_ROOT = FIXTURE_ROOT / "QaIosFixture"


def test_ios_fixture_info_plist_declares_privacy_and_deep_link() -> None:
    with (APP_ROOT / "Info.plist").open("rb") as stream:
        payload = plistlib.load(stream)

    assert payload["NSCameraUsageDescription"]
    assert payload["NSMicrophoneUsageDescription"]
    assert "qaweek19" in payload["CFBundleURLTypes"][0]["CFBundleURLSchemes"]


def test_ios_fixture_exposes_stable_accessibility_ids() -> None:
    source = (APP_ROOT / "ViewController.swift").read_text(encoding="utf-8")
    expected_ids = {
        "fixture-title",
        "fixture-status",
        "request-camera",
        "request-microphone",
        "request-notifications",
        "send-notification",
        "simulate-deep-link",
        "write-file",
        "read-file",
        "file-status",
        "background-status",
        "fixture-webview",
    }

    assert all(identifier in source for identifier in expected_ids)


def test_ios_fixture_xcode_project_and_shared_scheme_are_present() -> None:
    project = (
        FIXTURE_ROOT / "QaIosFixture.xcodeproj" / "project.pbxproj"
    ).read_text(encoding="utf-8")
    scheme_path = (
        FIXTURE_ROOT
        / "QaIosFixture.xcodeproj"
        / "xcshareddata"
        / "xcschemes"
        / "QaIosFixture.xcscheme"
    )
    scheme = ElementTree.parse(scheme_path).getroot()

    assert "AppDelegate.swift" in project
    assert "ViewController.swift" in project
    assert "QaIosFixture.app" in project
    assert scheme.tag == "Scheme"
    assert any(
        element.attrib.get("BlueprintName") == "QaIosFixture"
        for element in scheme.iter("BuildableReference")
    )
