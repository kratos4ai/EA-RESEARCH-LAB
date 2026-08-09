"""Immutable records for the canonical provenance chain."""

import math
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from ea_research_lab.domain.errors import ProvenanceInvariantError
from ea_research_lab.domain.evidence import (
    RawEvidenceManifest,
    RawEvidenceManifestRef,
)
from ea_research_lab.domain.identifiers import (
    AnalysisDefinitionId,
    AnalysisResultId,
    ArtifactId,
    BuildRecordId,
    DatasetId,
    EnvironmentConfigurationId,
    RunId,
    TestDefinitionRevisionId,
    TransformationId,
)
from ea_research_lab.domain.values import (
    DefinitionVersion,
    ReproducibilityAssessment,
    SchemaRef,
    SourceRevision,
)


def _freeze_json(value: object) -> object:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ProvenanceInvariantError(
                "Schema-referenced payload requires finite numbers."
            )
        return value
    if isinstance(value, Mapping):
        frozen: dict[str, object] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise ProvenanceInvariantError(
                    "Schema-referenced payload keys must be strings."
                )
            frozen[key] = _freeze_json(item)
        return MappingProxyType(frozen)
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_json(item) for item in value)
    raise ProvenanceInvariantError(
        "Schema-referenced payload must contain only JSON values."
    )


def _freeze_typed_tuple(
    values: object,
    expected_type: type,
    label: str,
) -> tuple:
    try:
        frozen = tuple(values)
    except TypeError as error:
        raise ProvenanceInvariantError(
            f"{label} must be an ordered collection."
        ) from error
    if any(not isinstance(value, expected_type) for value in frozen):
        raise ProvenanceInvariantError(
            f"{label} contains an invalid reference type."
        )
    return frozen


@dataclass(frozen=True, slots=True)
class SchemaReferencedPayload:
    schema_ref: SchemaRef
    value: Mapping[str, object]

    def __post_init__(self) -> None:
        if not isinstance(self.schema_ref, SchemaRef):
            raise ProvenanceInvariantError(
                "Schema-referenced payload requires a SchemaRef."
            )
        if not isinstance(self.value, Mapping):
            raise ProvenanceInvariantError(
                "Schema-referenced payload must be a JSON object."
            )
        object.__setattr__(self, "value", _freeze_json(self.value))


@dataclass(frozen=True, slots=True)
class BuildProvenance:
    source_revision: SourceRevision
    build_record_id: BuildRecordId
    build_configuration_id: EnvironmentConfigurationId
    build_configuration: SchemaReferencedPayload
    artifact_id: ArtifactId | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.source_revision, SourceRevision):
            raise ProvenanceInvariantError(
                "Build provenance requires a SourceRevision."
            )
        if not isinstance(self.build_record_id, BuildRecordId):
            raise ProvenanceInvariantError(
                "Build provenance requires a BuildRecordId."
            )
        if not isinstance(
            self.build_configuration_id, EnvironmentConfigurationId
        ) or not isinstance(self.build_configuration, SchemaReferencedPayload):
            raise ProvenanceInvariantError(
                "Build provenance requires an identified immutable configuration."
            )
        if self.artifact_id is not None and not isinstance(
            self.artifact_id, ArtifactId
        ):
            raise ProvenanceInvariantError(
                "Produced artifact reference must be an ArtifactId."
            )


@dataclass(frozen=True, slots=True)
class RunProvenance:
    artifact_id: ArtifactId
    test_definition_revision_id: TestDefinitionRevisionId
    environment_configuration_id: EnvironmentConfigurationId
    environment_configuration: SchemaReferencedPayload
    run_id: RunId
    execution_reproducibility: ReproducibilityAssessment

    def __post_init__(self) -> None:
        required = (
            (self.artifact_id, ArtifactId, "ArtifactId"),
            (
                self.test_definition_revision_id,
                TestDefinitionRevisionId,
                "TestDefinitionRevisionId",
            ),
            (
                self.environment_configuration_id,
                EnvironmentConfigurationId,
                "EnvironmentConfigurationId",
            ),
            (
                self.environment_configuration,
                SchemaReferencedPayload,
                "immutable environment configuration",
            ),
            (self.run_id, RunId, "RunId"),
            (
                self.execution_reproducibility,
                ReproducibilityAssessment,
                "execution reproducibility assessment",
            ),
        )
        for value, expected_type, label in required:
            if not isinstance(value, expected_type):
                raise ProvenanceInvariantError(
                    f"Run provenance requires {label}."
                )


@dataclass(frozen=True, slots=True)
class EvidenceProvenance:
    manifest: RawEvidenceManifest
    manifest_ref: RawEvidenceManifestRef

    def __post_init__(self) -> None:
        if not isinstance(self.manifest, RawEvidenceManifest) or not isinstance(
            self.manifest_ref, RawEvidenceManifestRef
        ):
            raise ProvenanceInvariantError(
                "Evidence provenance requires a sealed manifest and exact reference."
            )
        if self.manifest.manifest_id != self.manifest_ref.manifest_id:
            raise ProvenanceInvariantError(
                "Evidence manifest identity does not match its exact reference."
            )
        if self.manifest.run_id != self.manifest_ref.run_id:
            raise ProvenanceInvariantError(
                "Evidence manifest run does not match its exact reference."
            )


@dataclass(frozen=True, slots=True)
class DatasetProvenance:
    dataset_id: DatasetId
    transformation_id: TransformationId
    transformation_version: DefinitionVersion
    input_manifests: tuple[RawEvidenceManifestRef, ...] = ()
    input_datasets: tuple[DatasetId, ...] = ()
    transformation_parameters: SchemaReferencedPayload | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.dataset_id, DatasetId):
            raise ProvenanceInvariantError(
                "Dataset provenance requires a DatasetId."
            )
        if not isinstance(self.transformation_id, TransformationId) or not isinstance(
            self.transformation_version, DefinitionVersion
        ):
            raise ProvenanceInvariantError(
                "Dataset provenance requires transformation identity and version."
            )
        manifests = _freeze_typed_tuple(
            self.input_manifests,
            RawEvidenceManifestRef,
            "Input manifests",
        )
        datasets = _freeze_typed_tuple(
            self.input_datasets,
            DatasetId,
            "Input datasets",
        )
        if not manifests and not datasets:
            raise ProvenanceInvariantError(
                "Dataset provenance requires at least one input."
            )
        if len({item.manifest_id for item in manifests}) != len(manifests):
            raise ProvenanceInvariantError(
                "Dataset provenance cannot repeat an input manifest ID."
            )
        if len(set(datasets)) != len(datasets):
            raise ProvenanceInvariantError(
                "Dataset provenance cannot repeat an input dataset ID."
            )
        if self.transformation_parameters is not None and not isinstance(
            self.transformation_parameters, SchemaReferencedPayload
        ):
            raise ProvenanceInvariantError(
                "Transformation parameters must be schema-referenced and immutable."
            )
        object.__setattr__(self, "input_manifests", manifests)
        object.__setattr__(self, "input_datasets", datasets)


@dataclass(frozen=True, slots=True)
class AnalysisProvenance:
    analysis_result_id: AnalysisResultId
    analysis_definition_id: AnalysisDefinitionId
    analysis_version: DefinitionVersion
    analysis_parameters: SchemaReferencedPayload
    computation_environment_id: EnvironmentConfigurationId
    input_dataset_ids: tuple[DatasetId, ...]

    def __post_init__(self) -> None:
        required = (
            (self.analysis_result_id, AnalysisResultId, "AnalysisResultId"),
            (
                self.analysis_definition_id,
                AnalysisDefinitionId,
                "AnalysisDefinitionId",
            ),
            (self.analysis_version, DefinitionVersion, "analysis version"),
            (
                self.analysis_parameters,
                SchemaReferencedPayload,
                "immutable analysis parameters",
            ),
            (
                self.computation_environment_id,
                EnvironmentConfigurationId,
                "computation environment identity",
            ),
        )
        for value, expected_type, label in required:
            if not isinstance(value, expected_type):
                raise ProvenanceInvariantError(
                    f"Analysis provenance requires {label}."
                )
        datasets = _freeze_typed_tuple(
            self.input_dataset_ids,
            DatasetId,
            "Analysis input datasets",
        )
        if not datasets:
            raise ProvenanceInvariantError(
                "Analysis provenance requires at least one input dataset."
            )
        if len(set(datasets)) != len(datasets):
            raise ProvenanceInvariantError(
                "Analysis provenance cannot repeat an input dataset ID."
            )
        object.__setattr__(self, "input_dataset_ids", datasets)
