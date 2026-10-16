"""Runtime validation helpers that expose field-level contract failures."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel, ValidationError


class FieldViolation(BaseModel):
    """One contract error mapped to a JSON field path."""

    path: str
    error_type: str
    message: str


class ContractValidationError(ValueError):
    """Raised when a response payload violates its Pydantic contract."""

    def __init__(
        self,
        *,
        model_name: str,
        violations: list[FieldViolation],
    ) -> None:
        self.model_name = model_name
        self.violations = tuple(violations)
        details = "; ".join(
            f"{violation.path}: {violation.message}" for violation in violations
        )
        super().__init__(f"{model_name} contract violation: {details}")


def validate_contract[ModelT: BaseModel](
    model_type: type[ModelT],
    payload: Mapping[str, Any],
) -> ModelT:
    """Validate one payload and translate Pydantic errors into stable paths."""

    try:
        return model_type.model_validate(payload)
    except ValidationError as exc:
        violations = [
            FieldViolation(
                path=_json_path(error["loc"]),
                error_type=str(error["type"]),
                message=str(error["msg"]),
            )
            for error in exc.errors()
        ]
        raise ContractValidationError(
            model_name=model_type.__name__,
            violations=violations,
        ) from exc


def _json_path(location: tuple[str | int, ...]) -> str:
    path = "$"
    for segment in location:
        if isinstance(segment, int):
            path = f"{path}[{segment}]"
        else:
            path = f"{path}.{segment}"
    return path
