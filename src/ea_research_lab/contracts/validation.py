"""Exact-version JSON Schema validation at serialized trust boundaries."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections.abc import Mapping

from jsonschema import Draft202012Validator, FormatChecker

from ea_research_lab.contracts.catalog import SchemaCatalog, load_catalog
from ea_research_lab.domain.errors import InvalidValueError
from ea_research_lab.domain.values import (
    SchemaName,
    SchemaRef,
    SchemaVersion,
    Sha256Digest,
)


_EXTERNAL_ROOT_PATTERN = re.compile(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*")


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

    if schema_name == "build-input-manifest" and schema_version == "0.1.0":
        _validate_build_input_manifest(document)


def normalize_logical_path(value: str) -> str:
    """Return the provider-neutral NFC logical path used by identity v1."""

    if not isinstance(value, str) or not value:
        raise ContractValidationError(
            "schema_validation_failed", "$", "Logical path must be non-empty."
        )
    normalized = unicodedata.normalize("NFC", value)
    if (
        normalized.startswith("/")
        or normalized.endswith("/")
        or "\\" in normalized
        or re.match(r"^[A-Za-z]:", normalized)
        or normalized[:5].lower() == "file:"
        or any(unicodedata.category(character) == "Cc" for character in normalized)
    ):
        raise ContractValidationError(
            "schema_validation_failed", "$", "Logical path is not relative and portable."
        )
    segments = normalized.split("/")
    if any(segment in {"", ".", ".."} for segment in segments):
        raise ContractValidationError(
            "schema_validation_failed", "$", "Logical path has an invalid segment."
        )
    return normalized


def calculate_build_input_identity(
    primary: Mapping[str, object], dependencies: object
) -> Sha256Digest:
    """Calculate Build Input Identity v1 from normalized semantic fields.

    Dependencies are ordered by UTF-8 bytes of scope, root-or-empty, and path.
    The projection uses json.dumps with ensure_ascii=False, sort_keys=True,
    separators=(",", ":"), and allow_nan=False, then UTF-8 and SHA-256.
    """

    if not isinstance(primary, Mapping) or not isinstance(dependencies, (list, tuple)):
        raise ContractValidationError(
            "schema_validation_failed", "$", "Build input members are invalid."
        )

    projected_primary, primary_key = _project_member(primary, "$.primary")
    projected_dependencies: list[dict[str, object]] = []
    seen = {primary_key}
    for index, dependency in enumerate(dependencies):
        path = f"$.dependencies[{index}]"
        if not isinstance(dependency, Mapping):
            raise ContractValidationError(
                "schema_validation_failed", path, "Dependency must be an object."
            )
        projected, key = _project_member(dependency, path)
        if key in seen:
            raise ContractValidationError(
                "schema_validation_failed",
                f"{path}.logical_location",
                "Logical build-input locations must be unique.",
            )
        seen.add(key)
        projected_dependencies.append(projected)

    projected_dependencies.sort(
        key=lambda member: (
            member["scope"].encode("utf-8"),
            (member["root"] or "").encode("utf-8"),
            member["path"].encode("utf-8"),
        )
    )
    projection = {
        "primary": projected_primary,
        "dependencies": projected_dependencies,
    }
    projection_bytes = json.dumps(
        projection,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return Sha256Digest(hashlib.sha256(projection_bytes).hexdigest())


def _project_member(
    member: Mapping[str, object], path: str
) -> tuple[dict[str, object], tuple[str, str, str]]:
    location = member.get("logical_location")
    if not isinstance(location, Mapping):
        raise ContractValidationError(
            "schema_validation_failed",
            f"{path}.logical_location",
            "Logical location must be an object.",
        )
    scope = location.get("scope")
    raw_path = location.get("path")
    if scope not in {"workspace", "external"} or not isinstance(raw_path, str):
        raise ContractValidationError(
            "schema_validation_failed",
            f"{path}.logical_location",
            "Logical location is invalid.",
        )
    try:
        normalized_path = normalize_logical_path(raw_path)
    except ContractValidationError as error:
        raise ContractValidationError(
            "schema_validation_failed",
            f"{path}.logical_location.path",
            str(error),
        ) from error
    root = location.get("root")
    if scope == "workspace":
        if "root" in location:
            raise ContractValidationError(
                "schema_validation_failed",
                f"{path}.logical_location.root",
                "Workspace locations cannot declare a root.",
            )
        normalized_root = ""
        projected_root: str | None = None
    else:
        if not isinstance(root, str) or not _EXTERNAL_ROOT_PATTERN.fullmatch(root):
            raise ContractValidationError(
                "schema_validation_failed",
                f"{path}.logical_location.root",
                "External root must use lowercase kebab-case.",
            )
        normalized_root = root
        projected_root = root

    try:
        digest = Sha256Digest(member.get("content_digest"))
    except InvalidValueError as error:
        raise ContractValidationError(
            "schema_validation_failed",
            f"{path}.content_digest",
            str(error),
        ) from error
    projected = {
        "scope": scope,
        "root": projected_root,
        "path": normalized_path,
        "content_digest": str(digest),
    }
    return projected, (scope, normalized_root, normalized_path)


def _validate_build_input_manifest(document: Mapping[str, object]) -> None:
    members = [document["primary"], *document["dependencies"]]
    for index, member in enumerate(members):
        path = "$.primary" if index == 0 else f"$.dependencies[{index - 1}]"
        raw_path = member["logical_location"]["path"]
        if normalize_logical_path(raw_path) != raw_path:
            raise ContractValidationError(
                "schema_validation_failed",
                f"{path}.logical_location.path",
                "Logical path must already use Unicode NFC.",
            )
    actual = calculate_build_input_identity(
        document["primary"], document["dependencies"]
    )
    if str(actual) != document["build_input_identity"]:
        raise ContractValidationError(
            "schema_validation_failed",
            "$.build_input_identity",
            "Build Input Identity does not match the v1 semantic projection.",
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
