"""MetaEditor Build evidence to provider-neutral runtime metadata."""

from collections.abc import Mapping

from ea_research_lab.contracts import validate_document
from ea_research_lab.domain.provenance import SchemaReferencedPayload
from ea_research_lab.domain.semantic import ProviderRuntimeProjection
from ea_research_lab.domain.values import SchemaName, SchemaRef, SchemaVersion, Sha256Digest


_METAEDITOR_EVIDENCE = SchemaRef(
    SchemaName("metaeditor-build-evidence"), SchemaVersion(0, 1, 0)
)


def _plain(value: object) -> object:
    if isinstance(value, Mapping):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_plain(item) for item in value]
    return value


class MetaEditorBuildRuntimeProjector:
    def project(
        self, provider_evidence: SchemaReferencedPayload
    ) -> ProviderRuntimeProjection | None:
        if not isinstance(provider_evidence, SchemaReferencedPayload):
            raise TypeError("Build runtime projection requires provider evidence.")
        if provider_evidence.schema_ref != _METAEDITOR_EVIDENCE:
            return None
        document = _plain(provider_evidence.value)
        validate_document(document)
        return ProviderRuntimeProjection(
            "build",
            document["provider"],
            document["executable_version"],
            Sha256Digest(document["executable_digest"]),
        )
