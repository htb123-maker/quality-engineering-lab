"""Dependency-free JSON Schema compatibility checks for response contracts."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

Severity = Literal["breaking", "non_breaking"]


class CompatibilityFinding(BaseModel):
    """One compatibility difference between two schemas."""

    model_config = ConfigDict(frozen=True)

    severity: Severity
    path: str
    message: str


class CompatibilityReport(BaseModel):
    """Result of comparing an old schema with a candidate new schema."""

    model_config = ConfigDict(frozen=True)

    compatible: bool
    findings: tuple[CompatibilityFinding, ...] = Field(default_factory=tuple)


def compare_json_schemas(
    old_schema: Mapping[str, Any],
    new_schema: Mapping[str, Any],
) -> CompatibilityReport:
    """Compare response schemas from a consumer's perspective."""

    findings: list[CompatibilityFinding] = []
    _compare_schema(
        old_schema=old_schema,
        new_schema=new_schema,
        old_root=old_schema,
        new_root=new_schema,
        path="$",
        findings=findings,
    )
    compatible = not any(
        finding.severity == "breaking" for finding in findings
    )
    return CompatibilityReport(
        compatible=compatible,
        findings=tuple(findings),
    )


def _compare_schema(
    *,
    old_schema: Mapping[str, Any],
    new_schema: Mapping[str, Any],
    old_root: Mapping[str, Any],
    new_root: Mapping[str, Any],
    path: str,
    findings: list[CompatibilityFinding],
) -> None:
    old_resolved = _resolve_ref(old_schema, old_root)
    new_resolved = _resolve_ref(new_schema, new_root)

    old_type = old_resolved.get("type")
    new_type = new_resolved.get("type")
    if isinstance(old_type, str) and isinstance(new_type, str) and old_type != new_type:
        _add_breaking(
            findings,
            path,
            f"type changed from {old_type!r} to {new_type!r}",
        )
        return

    _compare_enums(old_resolved, new_resolved, path=path, findings=findings)

    old_properties = _object_mapping(old_resolved.get("properties"))
    new_properties = _object_mapping(new_resolved.get("properties"))
    if old_properties or new_properties:
        old_required = _string_set(old_resolved.get("required"))
        new_required = _string_set(new_resolved.get("required"))

        for name, old_property in old_properties.items():
            property_path = f"{path}.{name}"
            if name not in new_properties:
                _add_breaking(findings, property_path, "response field was removed")
                continue
            _compare_schema(
                old_schema=old_property,
                new_schema=new_properties[name],
                old_root=old_root,
                new_root=new_root,
                path=property_path,
                findings=findings,
            )

        for name in sorted(new_properties.keys() - old_properties.keys()):
            property_path = f"{path}.{name}"
            if name in new_required:
                _add_breaking(
                    findings,
                    property_path,
                    "new response field is required",
                )
            else:
                findings.append(
                    CompatibilityFinding(
                        severity="non_breaking",
                        path=property_path,
                        message="optional response field was added",
                    )
                )

        for name in sorted(new_required - old_required):
            property_path = f"{path}.{name}"
            if name in old_properties and not any(
                finding.path == property_path
                and finding.severity == "breaking"
                for finding in findings
            ):
                _add_breaking(
                    findings,
                    property_path,
                    "previously optional field became required",
                )

    old_items = _object_mapping(old_resolved.get("items"))
    new_items = _object_mapping(new_resolved.get("items"))
    if old_items and new_items:
        _compare_schema(
            old_schema=old_items,
            new_schema=new_items,
            old_root=old_root,
            new_root=new_root,
            path=f"{path}[]",
            findings=findings,
        )


def _compare_enums(
    old_schema: Mapping[str, Any],
    new_schema: Mapping[str, Any],
    *,
    path: str,
    findings: list[CompatibilityFinding],
) -> None:
    old_enum = _json_value_set(old_schema.get("enum"))
    new_enum = _json_value_set(new_schema.get("enum"))
    if not old_enum or not new_enum:
        return

    removed = old_enum - new_enum
    added = new_enum - old_enum
    if removed:
        _add_breaking(
            findings,
            path,
            f"enum values were removed: {sorted(removed)}",
        )
    if added:
        findings.append(
            CompatibilityFinding(
                severity="non_breaking",
                path=path,
                message=f"enum values were added: {sorted(added)}",
            )
        )


def _resolve_ref(
    schema: Mapping[str, Any],
    root: Mapping[str, Any],
) -> Mapping[str, Any]:
    reference = schema.get("$ref")
    if not isinstance(reference, str) or not reference.startswith("#/"):
        return schema

    current: Any = root
    for segment in reference[2:].split("/"):
        if not isinstance(current, Mapping) or segment not in current:
            return schema
        current = current[segment]
    return current if isinstance(current, Mapping) else schema


def _object_mapping(value: Any) -> Mapping[str, Mapping[str, Any]]:
    if not isinstance(value, Mapping):
        return {}
    result: dict[str, Mapping[str, Any]] = {}
    for key, item in value.items():
        if isinstance(key, str) and isinstance(item, Mapping):
            result[key] = item
    return result


def _string_set(value: Any) -> set[str]:
    if not isinstance(value, list):
        return set()
    return {item for item in value if isinstance(item, str)}


def _json_value_set(value: Any) -> set[str]:
    if not isinstance(value, list):
        return set()
    return {
        json.dumps(item, ensure_ascii=True, sort_keys=True)
        for item in value
    }


def _add_breaking(
    findings: list[CompatibilityFinding],
    path: str,
    message: str,
) -> None:
    findings.append(
        CompatibilityFinding(
            severity="breaking",
            path=path,
            message=message,
        )
    )
