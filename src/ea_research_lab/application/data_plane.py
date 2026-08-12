"""Storage-neutral Data Plane boundary for durable research facts."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol, Self

from ea_research_lab.application.build import (
    ArtifactAcceptance,
    BuildWorkflowResult,
)
from ea_research_lab.application.execution import (
    CollectedRawEvidence,
    RunExecutionResult,
)
from ea_research_lab.application.errors import ApplicationErrorCode
from ea_research_lab.contracts import calculate_build_input_identity, validate_document
from ea_research_lab.domain.analysis import AnalysisResult
from ea_research_lab.domain.build import BuildOutcome
from ea_research_lab.domain.dataset import Dataset
from ea_research_lab.domain.errors import InvalidValueError
from ea_research_lab.domain.evidence import RawEvidenceManifest, RawEvidenceManifestRef
from ea_research_lab.domain.identifiers import (
    AnalysisResultId,
    BuildRecordId,
    DatasetId,
    RunId,
    TestDefinitionRevisionId,
)
from ea_research_lab.domain.provenance import SchemaReferencedPayload
from ea_research_lab.domain.values import SchemaName, SchemaRef, SchemaVersion


BUILD_RECORD_REF = SchemaRef(
    SchemaName("build-record"), SchemaVersion(0, 2, 0)
)
BUILD_INPUT_MANIFEST_REF = SchemaRef(
    SchemaName("build-input-manifest"), SchemaVersion(0, 1, 0)
)
ARTIFACT_MANIFEST_REF = SchemaRef(
    SchemaName("artifact-manifest"), SchemaVersion(0, 1, 0)
)
TEST_DEFINITION_REF = SchemaRef(
    SchemaName("test-definition"), SchemaVersion(0, 1, 0)
)
RUN_MANIFEST_REF = SchemaRef(SchemaName("run-manifest"), SchemaVersion(0, 1, 0))
RAW_EVIDENCE_MANIFEST_REF = SchemaRef(
    SchemaName("raw-evidence-manifest"), SchemaVersion(0, 1, 0)
)
DATASET_MANIFEST_REF = SchemaRef(
    SchemaName("dataset-manifest"), SchemaVersion(0, 2, 0)
)
ANALYSIS_RESULT_REF = SchemaRef(
    SchemaName("analysis-result"), SchemaVersion(0, 2, 0)
)


class DataPlaneError(ValueError):
    """Safe public failure without physical storage details."""

    def __init__(self, code: ApplicationErrorCode, message: str) -> None:
        if code not in {
            ApplicationErrorCode.DATA_PLANE_FAILED,
            ApplicationErrorCode.DATA_INTEGRITY_FAILED,
        }:
            raise TypeError("Data Plane error code is invalid.")
        if not isinstance(message, str) or not message:
            raise TypeError("Data Plane error message is invalid.")
        self.code = code
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class DurableBuild:
    """Published Build facts, independent from workflow-only state."""

    build_record: SchemaReferencedPayload
    build_input_manifest: SchemaReferencedPayload | None = None
    artifact_acceptance: ArtifactAcceptance | None = None

    def __post_init__(self) -> None:
        if (
            not isinstance(self.build_record, SchemaReferencedPayload)
            or self.build_record.schema_ref != BUILD_RECORD_REF
        ):
            raise InvalidValueError("Durable Build requires Build Record 0.2.0.")
        if self.build_input_manifest is not None and (
            not isinstance(self.build_input_manifest, SchemaReferencedPayload)
            or self.build_input_manifest.schema_ref != BUILD_INPUT_MANIFEST_REF
        ):
            raise InvalidValueError(
                "Durable Build Input Manifest is invalid."
            )
        if self.artifact_acceptance is not None and not isinstance(
            self.artifact_acceptance, ArtifactAcceptance
        ):
            raise InvalidValueError("Durable Build Artifact is invalid.")

        record = _document(self.build_record)
        validate_document(record)
        _validate_embedded(record["build_configuration"])
        if "provider_evidence" in record:
            _validate_embedded(record["provider_evidence"])

        input_reference = record.get("build_input")
        if (input_reference is None) != (self.build_input_manifest is None):
            raise InvalidValueError("Durable Build Input linkage is invalid.")
        if self.build_input_manifest is not None:
            manifest = _document(self.build_input_manifest)
            validate_document(manifest)
            if not isinstance(input_reference, Mapping):
                raise InvalidValueError("Durable Build Input linkage is invalid.")
            identity = str(
                calculate_build_input_identity(
                    manifest["primary"], manifest["dependencies"]
                )
            )
            if (
                identity != manifest["build_input_identity"]
                or input_reference["schema_ref"]
                != str(BUILD_INPUT_MANIFEST_REF)
                or input_reference["build_input_identity"] != identity
            ):
                raise InvalidValueError(
                    "Durable Build Input identity is inconsistent."
                )

        outcome = BuildOutcome(record["status"])
        if outcome is BuildOutcome.SUCCEEDED:
            provider_evidence = record.get("provider_evidence")
            if self.artifact_acceptance is None or not isinstance(
                provider_evidence, Mapping
            ):
                raise InvalidValueError(
                    "Successful durable Build facts are incomplete."
                )
            artifact = self.artifact_acceptance.artifact
            artifact_manifest = _document(
                self.artifact_acceptance.artifact_manifest
            )
            validate_document(artifact_manifest)
            _validate_embedded(artifact_manifest["compiler"])
            if (
                record["build_record_id"] != str(artifact.build_record_id)
                or record["artifact_id"] != str(artifact.artifact_id)
                or artifact_manifest["source_revision"]
                != record["source_revision"]
                or artifact_manifest["compiler"]["schema_ref"]
                != provider_evidence["schema_ref"]
                or artifact_manifest["compiler"]["value"]
                != provider_evidence["value"]
            ):
                raise InvalidValueError(
                    "Durable Build Artifact provenance is inconsistent."
                )
        elif self.artifact_acceptance is not None:
            raise InvalidValueError("Failed durable Build cannot have an Artifact.")

    @classmethod
    def from_workflow_result(cls, result: BuildWorkflowResult) -> Self:
        if not isinstance(result, BuildWorkflowResult):
            raise TypeError("Durable Build requires a BuildWorkflowResult.")
        return cls(
            result.build_record,
            result.build_input_manifest,
            result.artifact_acceptance,
        )

    @property
    def build_record_id(self) -> BuildRecordId:
        return BuildRecordId.parse(self.build_record.value["build_record_id"])

    @property
    def outcome(self) -> BuildOutcome:
        return BuildOutcome(self.build_record.value["status"])


@dataclass(frozen=True, slots=True)
class DurableEvidence:
    """One sealed evidence revision and its exact immutable bytes."""

    manifest: RawEvidenceManifest
    payload: SchemaReferencedPayload
    reference: RawEvidenceManifestRef
    raw_evidence: tuple[CollectedRawEvidence, ...]

    def __post_init__(self) -> None:
        if (
            not isinstance(self.manifest, RawEvidenceManifest)
            or not isinstance(self.payload, SchemaReferencedPayload)
            or self.payload.schema_ref != RAW_EVIDENCE_MANIFEST_REF
            or not isinstance(self.reference, RawEvidenceManifestRef)
        ):
            raise InvalidValueError("Durable Raw Evidence is invalid.")
        try:
            evidence = tuple(self.raw_evidence)
        except TypeError as error:
            raise InvalidValueError("Durable Raw Evidence is invalid.") from error
        if any(not isinstance(item, CollectedRawEvidence) for item in evidence):
            raise InvalidValueError("Durable Raw Evidence is invalid.")
        document = _document(self.payload)
        validate_document(document)
        if (
            self.manifest.manifest_id != self.reference.manifest_id
            or self.manifest.run_id != self.reference.run_id
            or self.manifest.objects
            != tuple(item.evidence_object for item in evidence)
            or document != _evidence_document(self.manifest)
            or hashlib.sha256(_canonical_json(document)).hexdigest()
            != str(self.reference.content_digest)
        ):
            raise InvalidValueError("Durable Raw Evidence provenance is inconsistent.")
        object.__setattr__(self, "raw_evidence", evidence)

    @classmethod
    def from_execution_result(cls, result: RunExecutionResult) -> Self:
        if not isinstance(result, RunExecutionResult):
            raise TypeError("Durable Evidence requires a RunExecutionResult.")
        return cls(
            result.evidence_manifest,
            result.evidence_manifest_payload,
            result.evidence_manifest_ref,
            result.raw_evidence,
        )


@dataclass(frozen=True, slots=True)
class DurableRun:
    """Finalized Run facts without transient provider state."""

    test_definition: SchemaReferencedPayload
    run_manifest: SchemaReferencedPayload
    evidence_history: tuple[DurableEvidence, ...]

    def __post_init__(self) -> None:
        if (
            not isinstance(self.test_definition, SchemaReferencedPayload)
            or self.test_definition.schema_ref != TEST_DEFINITION_REF
            or not isinstance(self.run_manifest, SchemaReferencedPayload)
            or self.run_manifest.schema_ref != RUN_MANIFEST_REF
        ):
            raise InvalidValueError("Durable Run contracts are invalid.")
        test_definition = _document(self.test_definition)
        run = _document(self.run_manifest)
        validate_document(test_definition)
        validate_document(run)
        try:
            history = tuple(self.evidence_history)
        except TypeError as error:
            raise InvalidValueError(
                "Durable Run evidence history is invalid."
            ) from error
        if not history or any(
            not isinstance(item, DurableEvidence) for item in history
        ):
            raise InvalidValueError("Durable Run requires sealed Raw Evidence.")
        run_id = run["run_id"]
        for index, evidence in enumerate(history):
            if str(evidence.reference.run_id) != run_id:
                raise InvalidValueError("Durable Run evidence belongs to another Run.")
            if index and evidence.manifest.prior_manifest != history[
                index - 1
            ].reference:
                raise InvalidValueError(
                    "Durable Run evidence revision chain is invalid."
                )
        raw_reference = run.get("raw_evidence_manifest")
        if (
            not isinstance(raw_reference, Mapping)
            or raw_reference != _manifest_reference(history[-1].reference)
            or test_definition["test_definition_revision_id"]
            != run["test_definition_revision_id"]
            or test_definition["artifact_id"] != run["artifact_id"]
        ):
            raise InvalidValueError("Durable Run provenance is inconsistent.")
        object.__setattr__(self, "evidence_history", history)

    @classmethod
    def from_execution_result(
        cls,
        test_definition: SchemaReferencedPayload,
        result: RunExecutionResult,
    ) -> Self:
        if not isinstance(result, RunExecutionResult):
            raise TypeError("Durable Run requires a RunExecutionResult.")
        return cls(
            test_definition,
            result.run_manifest,
            (DurableEvidence.from_execution_result(result),),
        )

    @property
    def run_id(self) -> RunId:
        return RunId.parse(self.run_manifest.value["run_id"])

    @property
    def test_definition_revision_id(self) -> TestDefinitionRevisionId:
        return TestDefinitionRevisionId.parse(
            self.test_definition.value["test_definition_revision_id"]
        )


class DataPlane(Protocol):
    """The M1 Data Plane capability surface."""

    def publish_build(self, build: DurableBuild) -> None: ...

    def load_build(self, build_record_id: BuildRecordId) -> DurableBuild: ...

    def publish_run(self, run: DurableRun) -> None: ...

    def load_run(self, run_id: RunId) -> DurableRun: ...

    def publish_dataset(self, dataset: Dataset) -> None: ...

    def load_dataset(self, dataset_id: DatasetId) -> Dataset: ...

    def publish_analysis(self, result: AnalysisResult) -> None: ...

    def load_analysis(self, result_id: AnalysisResultId) -> AnalysisResult: ...


@dataclass(frozen=True, slots=True)
class CanonicalChainRequest:
    """Explicit roots for reconstructing one known research chain."""

    build_record_id: BuildRecordId
    run_id: RunId
    analysis_result_id: AnalysisResultId

    def __post_init__(self) -> None:
        if (
            not isinstance(self.build_record_id, BuildRecordId)
            or not isinstance(self.run_id, RunId)
            or not isinstance(self.analysis_result_id, AnalysisResultId)
        ):
            raise InvalidValueError("Canonical chain roots are invalid.")


@dataclass(frozen=True, slots=True)
class CanonicalChain:
    """Cross-validated durable facts; not a new persisted entity."""

    build: DurableBuild
    run: DurableRun
    datasets: tuple[Dataset, ...]
    analysis: AnalysisResult

    def __post_init__(self) -> None:
        if (
            not isinstance(self.build, DurableBuild)
            or not isinstance(self.run, DurableRun)
            or not isinstance(self.analysis, AnalysisResult)
        ):
            raise InvalidValueError("Canonical chain facts are invalid.")
        try:
            datasets = tuple(self.datasets)
        except TypeError as error:
            raise InvalidValueError("Canonical chain Datasets are invalid.") from error
        if not datasets or any(not isinstance(item, Dataset) for item in datasets):
            raise InvalidValueError("Canonical chain Datasets are invalid.")
        object.__setattr__(self, "datasets", datasets)


def reconstruct_canonical_chain(
    data_plane: DataPlane,
    request: CanonicalChainRequest,
) -> CanonicalChain:
    """Load and cross-validate one chain through the Data Plane port only."""

    if not isinstance(request, CanonicalChainRequest):
        raise TypeError("Canonical chain reconstruction requires explicit roots.")
    try:
        build = data_plane.load_build(request.build_record_id)
        run = data_plane.load_run(request.run_id)
        analysis = data_plane.load_analysis(request.analysis_result_id)
        analysis_inputs = _plain(analysis.envelope.value)["provenance"][
            "input_datasets"
        ]
        datasets = []
        pending = [DatasetId.parse(item["dataset_id"]) for item in analysis_inputs]
        loaded_ids: set[DatasetId] = set()
        while pending:
            dataset_id = pending.pop(0)
            if dataset_id in loaded_ids:
                continue
            dataset = data_plane.load_dataset(dataset_id)
            datasets.append(dataset)
            loaded_ids.add(dataset_id)
            pending.extend(dataset.provenance.input_datasets)
    except DataPlaneError:
        raise
    except (KeyError, TypeError, ValueError) as error:
        raise _chain_integrity_error() from error

    if build.artifact_acceptance is None:
        raise _chain_integrity_error()
    artifact_id = build.artifact_acceptance.artifact.artifact_id
    run_document = _plain(run.run_manifest.value)
    test_definition = _plain(run.test_definition.value)
    if (
        run_document["artifact_id"] != str(artifact_id)
        or test_definition["artifact_id"] != str(artifact_id)
        or run_document["test_definition_revision_id"]
        != test_definition["test_definition_revision_id"]
    ):
        raise _chain_integrity_error()

    evidence_revisions = {
        item.reference for item in run.evidence_history
    }
    datasets_by_id = {
        item.provenance.dataset_id: item for item in datasets
    }
    if not datasets or not any(
        dataset.provenance.input_manifests for dataset in datasets
    ):
        raise _chain_integrity_error()
    for dataset in datasets:
        if any(
            reference not in evidence_revisions
            for reference in dataset.provenance.input_manifests
        ) or any(
            input_id not in datasets_by_id
            for input_id in dataset.provenance.input_datasets
        ):
            raise _chain_integrity_error()

    direct_inputs = tuple(
        datasets_by_id[DatasetId.parse(item["dataset_id"])]
        for item in analysis_inputs
    )
    if analysis.input_datasets != direct_inputs or any(
        str(dataset.content.content_digest) != item["content_digest"]
        for dataset, item in zip(direct_inputs, analysis_inputs, strict=True)
    ):
        raise _chain_integrity_error()
    return CanonicalChain(build, run, tuple(datasets), analysis)


def validate_dataset(dataset: Dataset) -> None:
    if (
        not isinstance(dataset, Dataset)
        or dataset.manifest.schema_ref != DATASET_MANIFEST_REF
    ):
        raise InvalidValueError("Durable Dataset is invalid.")
    document = _document(dataset.manifest)
    validate_document(document)
    validate_document(_plain(dataset.content.payload.value))
    parameters = document.get("transformation_parameters")
    if parameters is not None:
        _validate_embedded(parameters)
    manifest_inputs = [
        _manifest_reference(reference)
        for reference in dataset.provenance.input_manifests
    ]
    if (
        document["dataset_id"] != str(dataset.provenance.dataset_id)
        or document["input_manifests"] != manifest_inputs
        or document["input_datasets"]
        != [str(value) for value in dataset.provenance.input_datasets]
        or document["transformation_id"]
        != str(dataset.provenance.transformation_id)
        or document["transformation_version"]
        != str(dataset.provenance.transformation_version)
        or _optional_embedded(dataset.provenance.transformation_parameters)
        != parameters
        or document["dataset_schema"] != str(dataset.content.payload.schema_ref)
        or document["content_digest"] != str(dataset.content.content_digest)
        or _canonical_json(_plain(dataset.content.payload.value))
        != dataset.content.canonical_bytes
        or hashlib.sha256(dataset.content.canonical_bytes).hexdigest()
        != str(dataset.content.content_digest)
        or document["created_at"] != str(dataset.created_at)
    ):
        raise InvalidValueError("Durable Dataset provenance is inconsistent.")


def validate_analysis(result: AnalysisResult) -> None:
    if (
        not isinstance(result, AnalysisResult)
        or result.envelope.schema_ref != ANALYSIS_RESULT_REF
    ):
        raise InvalidValueError("Durable Analysis Result is invalid.")
    document = _document(result.envelope)
    validate_document(document)
    validate_document(_plain(result.content.payload.value))
    _validate_embedded(document["provenance"]["analysis_parameters"])
    inputs = [
        {
            "dataset_id": str(dataset.provenance.dataset_id),
            "content_digest": str(dataset.content.content_digest),
        }
        for dataset in result.input_datasets
    ]
    provenance = document["provenance"]
    if (
        document["analysis_result_id"]
        != str(result.provenance.analysis_result_id)
        or document["result_schema"] != str(result.content.payload.schema_ref)
        or document["result_digest"] != str(result.content.content_digest)
        or document["result"] != _plain(result.content.payload.value)
        or provenance["input_datasets"] != inputs
        or provenance["analysis_definition_id"]
        != str(result.provenance.analysis_definition_id)
        or provenance["analysis_version"]
        != str(result.provenance.analysis_version)
        or provenance["analysis_parameters"]
        != _optional_embedded(result.provenance.analysis_parameters)
        or provenance["computation_environment_id"]
        != str(result.provenance.computation_environment_id)
        or document["created_at"] != str(result.created_at)
        or _canonical_json(_plain(result.content.payload.value))
        != result.content.canonical_bytes
        or hashlib.sha256(result.content.canonical_bytes).hexdigest()
        != str(result.content.content_digest)
    ):
        raise InvalidValueError("Durable Analysis provenance is inconsistent.")


def _validate_embedded(payload: object) -> None:
    if (
        not isinstance(payload, Mapping)
        or not isinstance(payload.get("schema_ref"), str)
        or not isinstance(payload.get("value"), Mapping)
    ):
        raise InvalidValueError("Durable embedded payload is invalid.")
    schema_ref = SchemaRef.parse(payload["schema_ref"])
    value = _plain(payload["value"])
    if not isinstance(value, dict):
        raise InvalidValueError("Durable embedded payload is invalid.")
    expected = SchemaRef(
        SchemaName(value["schema_name"]),
        SchemaVersion.parse(value["schema_version"]),
    )
    if schema_ref != expected:
        raise InvalidValueError("Durable embedded schema identity is inconsistent.")
    validate_document(value)


def _document(payload: SchemaReferencedPayload) -> dict[str, object]:
    document = _plain(payload.value)
    if not isinstance(document, dict):
        raise InvalidValueError("Durable document is invalid.")
    expected = SchemaRef(
        SchemaName(document["schema_name"]),
        SchemaVersion.parse(document["schema_version"]),
    )
    if payload.schema_ref != expected:
        raise InvalidValueError("Durable document schema identity is inconsistent.")
    return document


def _plain(value: object) -> object:
    if isinstance(value, Mapping):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_plain(item) for item in value]
    return value


def _canonical_json(document: object) -> bytes:
    return json.dumps(
        document,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _manifest_reference(reference: RawEvidenceManifestRef) -> dict[str, str]:
    return {
        "manifest_id": str(reference.manifest_id),
        "run_id": str(reference.run_id),
        "content_digest": str(reference.content_digest),
    }


def _optional_embedded(
    payload: SchemaReferencedPayload | None,
) -> dict[str, object] | None:
    if payload is None:
        return None
    return {
        "schema_ref": str(payload.schema_ref),
        "value": _plain(payload.value),
    }


def _evidence_document(manifest: RawEvidenceManifest) -> dict[str, object]:
    objects = []
    for item in manifest.objects:
        document: dict[str, object] = {
            "object_id": str(item.object_id),
            "media_type": item.media_type,
            "byte_length": item.byte_length,
            "content_digest": str(item.content_digest),
        }
        if item.payload_schema is not None:
            document["payload_schema"] = str(item.payload_schema)
        if item.provider_namespace is not None:
            document["provider_namespace"] = item.provider_namespace
        objects.append(document)
    document = {
        "schema_name": "raw-evidence-manifest",
        "schema_version": "0.1.0",
        "manifest_id": str(manifest.manifest_id),
        "run_id": str(manifest.run_id),
        "objects": objects,
        "sealed_at": str(manifest.sealed_at),
        "outcome": manifest.outcome.value,
    }
    if manifest.prior_manifest is not None:
        document["prior_manifest"] = _manifest_reference(manifest.prior_manifest)
    return document


def _chain_integrity_error() -> DataPlaneError:
    return DataPlaneError(
        ApplicationErrorCode.DATA_INTEGRITY_FAILED,
        "Canonical chain failed integrity checks.",
    )
