"""Validated inventory of the 50 unique iOS stage-acceptance tests."""

from __future__ import annotations

import ast
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

import yaml

_TEST_ID_PATTERN = re.compile(r"^IOS-[A-Z]+-\d{3}$")
_NODE_ID_PATTERN = re.compile(
    r"^tests/ios/test_[a-z0-9_]+\.py::test_[a-z0-9_]+$"
)
_DEVICE_SCOPES = {"current", "previous-major", "cloud"}


class IosTestArea(StrEnum):
    """Business areas represented in the Week 21 iOS suite."""

    SESSION = "session"
    NAVIGATION = "navigation"
    LOCATOR_WAIT = "locator_wait"
    SYSTEM_INTERACTION = "system_interaction"
    WEBVIEW = "webview"
    DEVICE_MATRIX = "device_matrix"
    NEGATIVE_DIAGNOSTICS = "negative_diagnostics"


class IosTestPriority(StrEnum):
    """Risk-based execution priority."""

    P0 = "P0"
    P1 = "P1"
    P2 = "P2"


class IosAutomationStatus(StrEnum):
    """Whether an inventory entry maps to executable automation."""

    AUTOMATED = "automated"
    SKIPPED = "skipped"
    NOT_IMPLEMENTED = "not_implemented"


@dataclass(frozen=True, slots=True)
class IosTestSpec:
    """One test with enough metadata to audit its purpose and evidence."""

    test_id: str
    node_id: str
    area: IosTestArea
    priority: IosTestPriority
    business_intent: str
    preconditions: tuple[str, ...]
    steps: tuple[str, ...]
    expected_result: str
    device_scope: tuple[str, ...]
    automation_status: IosAutomationStatus
    evidence_path: str
    known_limitation: str | None = None


@dataclass(frozen=True, slots=True)
class IosTestInventory:
    """The validated iOS test inventory and its declared target size."""

    expected_count: int
    tests: tuple[IosTestSpec, ...]

    def by_priority(self, *priorities: IosTestPriority) -> tuple[str, ...]:
        """Return pytest node IDs in stable inventory order."""

        selected = set(priorities)
        return tuple(
            test.node_id for test in self.tests if test.priority in selected
        )

    def priorities(self) -> Counter[IosTestPriority]:
        """Count tests by execution priority."""

        return Counter(test.priority for test in self.tests)


def discover_ios_test_node_ids(test_root: Path) -> tuple[str, ...]:
    """Discover module-level pytest functions without importing Appium tests."""

    node_ids: list[str] = []
    project_root = test_root.parent.parent
    for path in sorted(test_root.glob("test_*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        relative = path.relative_to(project_root).as_posix()
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name.startswith("test_"):
                    node_ids.append(f"{relative}::{node.name}")
    return tuple(node_ids)


def load_ios_test_inventory(
    inventory_path: Path,
    *,
    project_root: Path,
    expected_count: int = 50,
) -> IosTestInventory:
    """Load and validate one inventory against the collected iOS test source."""

    try:
        payload = yaml.safe_load(inventory_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"iOS test inventory not found: {inventory_path}") from exc

    if not isinstance(payload, Mapping):
        raise ValueError("iOS test inventory must be a YAML mapping")
    if payload.get("version") != 1:
        raise ValueError("iOS test inventory version must be 1")
    declared_count = payload.get("expected_count")
    if declared_count != expected_count:
        raise ValueError(
            f"iOS test inventory expected_count must be {expected_count}"
        )
    raw_tests = payload.get("tests")
    if not isinstance(raw_tests, list):
        raise ValueError("iOS test inventory must contain a tests list")
    if len(raw_tests) != expected_count:
        raise ValueError(
            f"iOS test inventory must contain exactly {expected_count} tests; "
            f"found {len(raw_tests)}"
        )

    tests = tuple(
        _parse_test(raw, index)
        for index, raw in enumerate(raw_tests, start=1)
    )
    _validate_unique_values(tests)

    discovered = discover_ios_test_node_ids(project_root / "tests" / "ios")
    declared_nodes = {test.node_id for test in tests}
    missing = set(discovered).difference(declared_nodes)
    unknown = declared_nodes.difference(discovered)
    if missing or unknown:
        parts: list[str] = []
        if missing:
            parts.append(f"unmapped tests: {', '.join(sorted(missing))}")
        if unknown:
            parts.append(f"unknown node IDs: {', '.join(sorted(unknown))}")
        raise ValueError("iOS test inventory/source mismatch: " + "; ".join(parts))

    return IosTestInventory(expected_count=expected_count, tests=tests)


def _parse_test(raw: object, index: int) -> IosTestSpec:
    if not isinstance(raw, Mapping):
        raise ValueError(f"iOS inventory test {index} must be a mapping")

    test_id = _required_string(raw, "id", index)
    if _TEST_ID_PATTERN.fullmatch(test_id) is None:
        raise ValueError(f"invalid iOS test id: {test_id!r}")
    node_id = _required_string(raw, "node_id", index)
    if _NODE_ID_PATTERN.fullmatch(node_id) is None:
        raise ValueError(f"invalid iOS pytest node ID: {node_id!r}")

    device_scope = _string_sequence(raw, "device_scope", index)
    unknown_scopes = set(device_scope).difference(_DEVICE_SCOPES)
    if unknown_scopes:
        raise ValueError(
            f"test {test_id!r} has unknown device scope(s): "
            f"{', '.join(sorted(unknown_scopes))}"
        )

    known_limitation = _optional_string(raw, "known_limitation", index)
    automation_status = _enum_value(
        IosAutomationStatus,
        _required_string(raw, "automation_status", index),
        "automation_status",
        test_id,
    )
    if automation_status is not IosAutomationStatus.AUTOMATED:
        raise ValueError(
            f"test {test_id!r} does not count toward 50 because it is "
            f"{automation_status.value}"
        )
    if known_limitation is None and test_id == "IOS-WEBVIEW-001":
        raise ValueError("IOS-WEBVIEW-001 must document its cloud limitation")

    return IosTestSpec(
        test_id=test_id,
        node_id=node_id,
        area=_enum_value(
            IosTestArea,
            _required_string(raw, "area", index),
            "area",
            test_id,
        ),
        priority=_enum_value(
            IosTestPriority,
            _required_string(raw, "priority", index),
            "priority",
            test_id,
        ),
        business_intent=_required_string(raw, "business_intent", index),
        preconditions=_string_sequence(raw, "preconditions", index),
        steps=_string_sequence(raw, "steps", index),
        expected_result=_required_string(raw, "expected_result", index),
        device_scope=device_scope,
        automation_status=automation_status,
        evidence_path=_required_string(raw, "evidence_path", index),
        known_limitation=known_limitation,
    )


def _validate_unique_values(tests: Sequence[IosTestSpec]) -> None:
    for field, values in (
        ("test IDs", [test.test_id for test in tests]),
        ("node IDs", [test.node_id for test in tests]),
        (
            "business intents",
            [test.business_intent.casefold().strip() for test in tests],
        ),
    ):
        duplicates = sorted(
            value for value, count in Counter(values).items() if count > 1
        )
        if duplicates:
            raise ValueError(
                f"duplicate iOS inventory {field}: {', '.join(duplicates)}"
            )

    counts = Counter(test.priority for test in tests)
    if counts[IosTestPriority.P0] == 0:
        raise ValueError("iOS inventory must contain at least one P0 test")


def _required_string(raw: Mapping[object, object], key: str, index: int) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"iOS inventory test {index} requires string field {key!r}")
    return value.strip()


def _optional_string(
    raw: Mapping[object, object],
    key: str,
    index: int,
) -> str | None:
    value = raw.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(
            f"iOS inventory test {index} field {key!r} must be a non-empty string"
        )
    return value.strip()


def _string_sequence(
    raw: Mapping[object, object],
    key: str,
    index: int,
) -> tuple[str, ...]:
    value = raw.get(key)
    if not isinstance(value, list) or not value:
        raise ValueError(
            f"iOS inventory test {index} requires a non-empty {key!r} list"
        )
    result: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise ValueError(
                f"iOS inventory test {index} has invalid {key!r} entry"
            )
        result.append(item.strip())
    return tuple(result)


def _enum_value[EnumT: StrEnum](
    enum_type: type[EnumT],
    value: str,
    field: str,
    test_id: str,
) -> EnumT:
    try:
        return enum_type(value)
    except ValueError as exc:
        raise ValueError(
            f"test {test_id!r} has unsupported {field}: {value!r}"
        ) from exc
