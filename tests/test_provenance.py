import unittest
from dataclasses import FrozenInstanceError

from ea_research_lab.application.identity import new_entity_id
from ea_research_lab.domain.errors import InvalidValueError, ProvenanceInvariantError
from ea_research_lab.domain.evidence import (
    EvidenceCollectionOutcome,
    RawEvidenceManifest,
    RawEvidenceManifestRef,
    RawEvidenceObject,
)
from ea_research_lab.domain.identifiers import (
    AnalysisDefinitionId,
    AnalysisResultId,
    ArtifactId,
    BuildRecordId,
    DatasetId,
    EnvironmentConfigurationId,
    RawEvidenceManifestId,
    RawEvidenceObjectId,
    RunId,
    TestDefinitionRevisionId,
    TransformationId,
)
from ea_research_lab.domain.provenance import (
    AnalysisProvenance,
    BuildProvenance,
    DatasetProvenance,
    EvidenceProvenance,
    RunProvenance,
    SchemaReferencedPayload,
)
from ea_research_lab.domain.values import (
    DefinitionVersion,
    ReproducibilityAssessment,
    ReproducibilityLevel,
    ReproducibilityReason,
    SchemaName,
    SchemaRef,
    SchemaVersion,
    Sha256Digest,
    SourceRevision,
    UtcTimestamp,
)


def _schema_ref(name: str) -> SchemaRef:
    return SchemaRef(SchemaName(name), SchemaVersion(0, 1, 0))


def _payload(name: str, value: dict[str, object]) -> SchemaReferencedPayload:
    return SchemaReferencedPayload(_schema_ref(name), value)


class ReproducibilityTests(unittest.TestCase):
    def test_all_levels_are_explicit_non_boolean_values(self) -> None:
        self.assertEqual(
            {level.name for level in ReproducibilityLevel},
            {"EXACT", "EQUIVALENT", "BEST_EFFORT", "UNAVAILABLE"},
        )
        exact = ReproducibilityAssessment(ReproducibilityLevel.EXACT)
        self.assertIs(exact.level, ReproducibilityLevel.EXACT)
        with self.assertRaises(InvalidValueError):
            ReproducibilityAssessment(True)

    def test_limited_levels_require_ordered_reasons(self) -> None:
        for level in (
            ReproducibilityLevel.BEST_EFFORT,
            ReproducibilityLevel.UNAVAILABLE,
        ):
            with self.subTest(level=level), self.assertRaises(InvalidValueError):
                ReproducibilityAssessment(level)

        reasons = [
            ReproducibilityReason(
                "missing_dependency",
                "A required external dependency is unavailable.",
            ),
            ReproducibilityReason(
                "capability_not_guaranteed",
                "The required replay capability is not guaranteed.",
            ),
        ]
        assessment = ReproducibilityAssessment(
            ReproducibilityLevel.BEST_EFFORT,
            reasons,
        )

        self.assertIsInstance(assessment.reasons, tuple)
        self.assertEqual(assessment.reasons, tuple(reasons))

    def test_invalid_reason_is_rejected(self) -> None:
        for code, detail in (("MissingDependency", "Detail"), ("missing", " ")):
            with self.subTest(code=code), self.assertRaises(InvalidValueError):
                ReproducibilityReason(code, detail)


class ProvenanceTests(unittest.TestCase):
    def test_schema_referenced_payload_is_deeply_immutable(self) -> None:
        source = {"options": [{"name": "declared"}]}
        payload = _payload("execution-configuration", source)
        source["options"][0]["name"] = "changed"

        self.assertEqual(payload.value["options"][0]["name"], "declared")
        with self.assertRaises(TypeError):
            payload.value["other"] = True
        with self.assertRaises(FrozenInstanceError):
            payload.schema_ref = _schema_ref("other")

    def test_schema_referenced_payload_rejects_unsafe_values(self) -> None:
        for value in ({"unsafe": object()}, {"number": float("nan")}):
            with self.subTest(value=value), self.assertRaises(
                ProvenanceInvariantError
            ):
                _payload("parameters", value)

    def test_complete_canonical_chain_is_representable(self) -> None:
        source_revision = SourceRevision(
            vcs_kind="git",
            repository="ea-research-lab",
            revision="d5a326d516b2f56da2a8043c7ebfd7ffd8744f20",
            is_dirty=False,
        )
        artifact_id = new_entity_id(ArtifactId)
        build = BuildProvenance(
            source_revision=source_revision,
            build_record_id=new_entity_id(BuildRecordId),
            build_configuration_id=new_entity_id(EnvironmentConfigurationId),
            build_configuration=_payload("build-configuration", {"mode": "release"}),
            artifact_id=artifact_id,
        )

        run_id = new_entity_id(RunId)
        run = RunProvenance(
            artifact_id=artifact_id,
            test_definition_revision_id=new_entity_id(TestDefinitionRevisionId),
            environment_configuration_id=new_entity_id(
                EnvironmentConfigurationId
            ),
            environment_configuration=_payload(
                "execution-configuration",
                {"profile": "declared"},
            ),
            run_id=run_id,
            execution_reproducibility=ReproducibilityAssessment(
                ReproducibilityLevel.EQUIVALENT,
                (
                    ReproducibilityReason(
                        "bitwise_replay_not_guaranteed",
                        "Equivalent inputs are captured without a bitwise replay claim.",
                    ),
                ),
            ),
        )

        raw_object = RawEvidenceObject(
            object_id=new_entity_id(RawEvidenceObjectId),
            media_type="application/octet-stream",
            byte_length=16,
            content_digest=Sha256Digest("a" * 64),
        )
        manifest = RawEvidenceManifest(
            manifest_id=new_entity_id(RawEvidenceManifestId),
            run_id=run_id,
            objects=(raw_object,),
            sealed_at=UtcTimestamp.parse("2026-08-09T16:00:00Z"),
            outcome=EvidenceCollectionOutcome.COMPLETED,
        )
        manifest_ref = RawEvidenceManifestRef(
            manifest.manifest_id,
            run_id,
            Sha256Digest("b" * 64),
        )
        evidence = EvidenceProvenance(manifest, manifest_ref)

        dataset_id = new_entity_id(DatasetId)
        dataset = DatasetProvenance(
            dataset_id=dataset_id,
            transformation_id=new_entity_id(TransformationId),
            transformation_version=DefinitionVersion("normalize-v1"),
            input_manifests=(manifest_ref,),
            transformation_parameters=_payload(
                "transformation-parameters",
                {"mode": "lossless"},
            ),
        )
        analysis = AnalysisProvenance(
            analysis_result_id=new_entity_id(AnalysisResultId),
            analysis_definition_id=new_entity_id(AnalysisDefinitionId),
            analysis_version=DefinitionVersion("summary-v1"),
            analysis_parameters=_payload("analysis-parameters", {}),
            computation_environment_id=new_entity_id(
                EnvironmentConfigurationId
            ),
            input_dataset_ids=(dataset_id,),
        )

        self.assertEqual(build.artifact_id, run.artifact_id)
        self.assertEqual(run.run_id, evidence.manifest.run_id)
        self.assertIn(evidence.manifest_ref, dataset.input_manifests)
        self.assertIn(dataset.dataset_id, analysis.input_dataset_ids)
        self.assertEqual(build.source_revision, source_revision)

    def test_invalid_reference_relationships_are_rejected(self) -> None:
        run_id = new_entity_id(RunId)
        manifest = RawEvidenceManifest(
            new_entity_id(RawEvidenceManifestId),
            run_id,
            (),
            UtcTimestamp.parse("2026-08-09T16:00:00Z"),
            EvidenceCollectionOutcome.FAILED,
        )
        mismatched_ref = RawEvidenceManifestRef(
            new_entity_id(RawEvidenceManifestId),
            run_id,
            Sha256Digest("c" * 64),
        )

        with self.assertRaises(ProvenanceInvariantError):
            EvidenceProvenance(manifest, mismatched_ref)
        with self.assertRaises(ProvenanceInvariantError):
            BuildProvenance(
                source_revision=None,
                build_record_id=new_entity_id(BuildRecordId),
                build_configuration_id=new_entity_id(
                    EnvironmentConfigurationId
                ),
                build_configuration=_payload("build-configuration", {}),
            )
        with self.assertRaises(ProvenanceInvariantError):
            RunProvenance(
                artifact_id=new_entity_id(ArtifactId),
                test_definition_revision_id=new_entity_id(
                    TestDefinitionRevisionId
                ),
                environment_configuration_id=new_entity_id(
                    EnvironmentConfigurationId
                ),
                environment_configuration=_payload(
                    "execution-configuration",
                    {},
                ),
                run_id=None,
                execution_reproducibility=ReproducibilityAssessment(
                    ReproducibilityLevel.EQUIVALENT
                ),
            )
        with self.assertRaises(ProvenanceInvariantError):
            DatasetProvenance(
                dataset_id=new_entity_id(DatasetId),
                transformation_id=new_entity_id(TransformationId),
                transformation_version=DefinitionVersion("v1"),
            )
        with self.assertRaises(ProvenanceInvariantError):
            AnalysisProvenance(
                analysis_result_id=new_entity_id(AnalysisResultId),
                analysis_definition_id=new_entity_id(AnalysisDefinitionId),
                analysis_version=DefinitionVersion("v1"),
                analysis_parameters=_payload("analysis-parameters", {}),
                computation_environment_id=new_entity_id(
                    EnvironmentConfigurationId
                ),
                input_dataset_ids=(),
            )

    def test_provenance_records_are_frozen(self) -> None:
        build = BuildProvenance(
            source_revision=SourceRevision(
                "git",
                "ea-research-lab",
                "d5a326d516b2f56da2a8043c7ebfd7ffd8744f20",
                False,
            ),
            build_record_id=new_entity_id(BuildRecordId),
            build_configuration_id=new_entity_id(EnvironmentConfigurationId),
            build_configuration=_payload("build-configuration", {}),
        )

        with self.assertRaises(FrozenInstanceError):
            build.artifact_id = new_entity_id(ArtifactId)


if __name__ == "__main__":
    unittest.main()
