"""Provider-neutral experiment-context projection port."""

from typing import Protocol

from ea_research_lab.domain.provenance import SchemaReferencedPayload
from ea_research_lab.domain.semantic import ExperimentContextProjection


class ExperimentContextProjector(Protocol):
    def project(
        self, execution_configuration: SchemaReferencedPayload
    ) -> ExperimentContextProjection | None: ...
