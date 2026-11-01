"""Unit tests for the Week 21 iOS inventory contract."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from qa_core.platforms.ios.inventory import (
    IosAutomationStatus,
    IosTestPriority,
    load_ios_test_inventory,
)


def test_week21_inventory_maps_exactly_fifty_ios_tests() -> None:
    project_root = Path(__file__).resolve().parents[2]
    inventory = load_ios_test_inventory(
        project_root / "configs" / "ios-test-inventory.yaml",
        project_root=project_root,
    )

    assert inventory.expected_count == 50
    assert len(inventory.tests) == 50
    assert inventory.priorities()[IosTestPriority.P0] == 20
    assert len(inventory.by_priority(IosTestPriority.P0)) == 20


def test_inventory_rejects_duplicate_ids_and_non_automated_entries(
    tmp_path: Path,
) -> None:
    tests_root = tmp_path / "tests" / "ios"
    tests_root.mkdir(parents=True)
    (tests_root / "test_example.py").write_text(
        "def test_one():\n    pass\n\ndef test_two():\n    pass\n",
        encoding="utf-8",
    )
    entry = _inventory_entry(
        test_id="IOS-EXAMPLE-001",
        node_id="tests/ios/test_example.py::test_one",
        business_intent="First unique intent",
    )
    duplicate = {
        **entry,
        "node_id": "tests/ios/test_example.py::test_two",
        "business_intent": "Second unique intent",
    }
    path = _write_inventory(tmp_path, [entry, duplicate], expected_count=2)

    with pytest.raises(ValueError, match="duplicate iOS inventory test IDs"):
        load_ios_test_inventory(path, project_root=tmp_path, expected_count=2)

    duplicate["id"] = "IOS-EXAMPLE-002"
    duplicate["automation_status"] = IosAutomationStatus.SKIPPED.value
    _write_inventory(tmp_path, [entry, duplicate], expected_count=2)
    with pytest.raises(ValueError, match="does not count toward 50"):
        load_ios_test_inventory(path, project_root=tmp_path, expected_count=2)


def test_inventory_rejects_source_mismatch(tmp_path: Path) -> None:
    tests_root = tmp_path / "tests" / "ios"
    tests_root.mkdir(parents=True)
    (tests_root / "test_example.py").write_text(
        "def test_one():\n    pass\n\ndef test_unmapped():\n    pass\n",
        encoding="utf-8",
    )
    path = _write_inventory(
        tmp_path,
        [
            _inventory_entry(
                test_id="IOS-EXAMPLE-001",
                node_id="tests/ios/test_example.py::test_one",
                business_intent="Only mapped intent",
            )
        ],
        expected_count=1,
    )

    with pytest.raises(ValueError, match="unmapped tests"):
        load_ios_test_inventory(path, project_root=tmp_path, expected_count=1)


def _inventory_entry(
    *,
    test_id: str,
    node_id: str,
    business_intent: str,
) -> dict[str, object]:
    return {
        "id": test_id,
        "node_id": node_id,
        "area": "session",
        "priority": "P0",
        "business_intent": business_intent,
        "preconditions": ["fixture ready"],
        "steps": ["run test"],
        "expected_result": "the assertion passes",
        "device_scope": ["current"],
        "automation_status": "automated",
        "evidence_path": "artifacts/example/",
    }


def _write_inventory(
    root: Path,
    tests: list[dict[str, object]],
    *,
    expected_count: int,
) -> Path:
    path = root / "inventory.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "version": 1,
                "expected_count": expected_count,
                "tests": tests,
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    return path
