"""Provider-specific runtime facts projected into bounded semantic metadata."""

from typing import Protocol

from ea_research_lab.domain.provenance import SchemaReferencedPayload
from ea_research_lab.domain.semantic import ProviderRuntimeProjection


class BuildRuntimeProjector(Protocol):
    def project(
        self, provider_evidence: SchemaReferencedPayload
    ) -> ProviderRuntimeProjection | None: ...
