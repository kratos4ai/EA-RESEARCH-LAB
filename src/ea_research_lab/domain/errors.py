"""Transport-neutral domain errors."""

from typing import ClassVar


class DomainError(ValueError):
    """Base class for rejected domain values and invariants."""

    code: ClassVar[str] = "domain_error"


class InvalidIdentifierError(DomainError):
    code = "invalid_identifier"


class InvalidValueError(DomainError):
    code = "invalid_value"


class ProvenanceInvariantError(DomainError):
    code = "invalid_provenance"


class EvidenceInvariantError(DomainError):
    code = "invalid_evidence_manifest"
