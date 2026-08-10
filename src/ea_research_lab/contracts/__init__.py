"""Versioned serialized-contract loading and validation."""

from ea_research_lab.contracts.catalog import SchemaCatalog, load_catalog
from ea_research_lab.contracts.validation import (
    ContractValidationError,
    build_validator,
    calculate_build_input_identity,
    normalize_logical_path,
    validate_document,
)

__all__ = [
    "ContractValidationError",
    "SchemaCatalog",
    "build_validator",
    "calculate_build_input_identity",
    "load_catalog",
    "normalize_logical_path",
    "validate_document",
]
