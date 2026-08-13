"""MT5 execution configuration to provider-neutral semantic projection."""

from collections.abc import Mapping
from datetime import date
from decimal import Decimal

from ea_research_lab.contracts import validate_document
from ea_research_lab.domain.provenance import SchemaReferencedPayload
from ea_research_lab.domain.semantic import ExperimentContextProjection
from ea_research_lab.domain.values import SchemaName, SchemaRef, SchemaVersion


_EXECUTION_CONFIGURATION = SchemaRef(
    SchemaName("mt5-strategy-tester-execution"), SchemaVersion(0, 1, 0)
)


def _plain(value: object) -> object:
    if isinstance(value, Mapping):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_plain(item) for item in value]
    return value


class Mt5ExperimentContextProjector:
    def project(
        self, execution_configuration: SchemaReferencedPayload
    ) -> ExperimentContextProjection | None:
        if not isinstance(execution_configuration, SchemaReferencedPayload):
            raise TypeError("Experiment projection requires a configuration payload.")
        if execution_configuration.schema_ref != _EXECUTION_CONFIGURATION:
            return None
        document = _plain(execution_configuration.value)
        validate_document(document)
        return ExperimentContextProjection(
            document["symbol"],
            document["period"],
            date.fromisoformat(document["from_date"]),
            date.fromisoformat(document["to_date"]),
            Decimal(str(document["deposit"])),
            document["currency"],
            document["leverage"],
        )
