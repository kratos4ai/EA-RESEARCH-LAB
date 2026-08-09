"""Exact-version JSON Schema validation at serialized trust boundaries."""

from __future__ import annotations

import json
from collections.abc import Mapping

from jsonschema import Draft202012Validator, FormatChecker

from ea_research_lab.contracts.catalog import SchemaCatalog, load_catalog
from ea_research_lab.domain.errors import InvalidValueError
from ea_research_lab.domain.values import SchemaName, SchemaRef, SchemaVersion


class ContractValidationError(ValueError):
    """Stable contract-validation failure with a document path."""

    def __init__(self, code: str, path: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.path = path


def build_validator(
    schema: Mapping[str, object], catalog: SchemaCatalog
) -> Draft202012Validator:
    """Build a Draft 2020-12 validator with formats explicitly enabled."""

    return Draft202012Validator(
        schema,
        registry=catalog.registry,
        format_checker=FormatChecker(),
    )


def validate_document(
    document: Mapping[str, object], catalog: SchemaCatalog | None = None
) -> None:
    """Validate one document against its exact locally supported contract."""

    if not isinstance(document, Mapping):
        raise ContractValidationError(
            "schema_validation_failed", "$", "Document must be a JSON object."
        )

    schema_name = document.get("schema_name")
    schema_version = document.get("schema_version")
    if not isinstance(schema_name, str):
        raise ContractValidationError(
            "schema_validation_failed",
            "$.schema_name",
            "schema_name must be a string.",
        )
    if not isinstance(schema_version, str):
        raise ContractValidationError(
            "schema_validation_failed",
            "$.schema_version",
            "schema_version must be a string.",
        )

    try:
        parsed_name = SchemaName(schema_name)
    except InvalidValueError as error:
        raise ContractValidationError(
            "schema_validation_failed",
            "$.schema_name",
            "Invalid schema discriminator.",
        ) from error
    try:
        parsed_version = SchemaVersion.parse(schema_version)
    except InvalidValueError as error:
        raise ContractValidationError(
            "schema_validation_failed",
            "$.schema_version",
            "Invalid schema discriminator.",
        ) from error

    schema_ref = SchemaRef(parsed_name, parsed_version)

    active_catalog = catalog if catalog is not None else load_catalog()
    schema = active_catalog.get(schema_ref)
    if schema is None or schema_name == "common":
        supported_name = any(
            candidate.name == parsed_name for candidate in active_catalog.schemas
        )
        raise ContractValidationError(
            "unsupported_schema",
            "$.schema_version" if supported_name else "$.schema_name",
            f"Unsupported schema: {schema_ref}",
        )

    validator = build_validator(schema, active_catalog)
    errors = sorted(
        validator.iter_errors(document),
        key=lambda error: (
            tuple(str(part) for part in error.absolute_path),
            error.message,
        ),
    )
    if errors:
        error = errors[0]
        raise ContractValidationError(
            "schema_validation_failed",
            _validation_error_path(error),
            error.message,
        )


def _json_path(parts: object) -> str:
    path = "$"
    for part in parts:
        if isinstance(part, int):
            path += f"[{part}]"
        elif isinstance(part, str) and part.isidentifier():
            path += f".{part}"
        else:
            path += f"[{json.dumps(part)}]"
    return path


def _validation_error_path(error: object) -> str:
    parts = list(error.absolute_path)
    if error.validator == "required":
        missing = next(
            field for field in error.validator_value if field not in error.instance
        )
        parts.append(missing)
    return _json_path(parts)
