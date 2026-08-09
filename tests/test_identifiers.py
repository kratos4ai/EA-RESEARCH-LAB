import unittest
from dataclasses import FrozenInstanceError
from uuid import uuid4, uuid7

from ea_research_lab.application.identity import new_entity_id
from ea_research_lab.domain.errors import InvalidIdentifierError
from ea_research_lab.domain.identifiers import (
    AnalysisDefinitionId,
    AnalysisResultId,
    ArtifactId,
    BuildRecordId,
    DatasetId,
    EntityId,
    EnvironmentConfigurationId,
    RawEvidenceManifestId,
    RawEvidenceObjectId,
    RequestId,
    RunId,
    TestDefinitionId,
    TestDefinitionRevisionId,
    TransformationId,
)


IDENTIFIER_TYPES = (
    (BuildRecordId, "build"),
    (ArtifactId, "artifact"),
    (TestDefinitionId, "testdef"),
    (TestDefinitionRevisionId, "testrev"),
    (EnvironmentConfigurationId, "envcfg"),
    (RunId, "run"),
    (RawEvidenceObjectId, "rawobj"),
    (RawEvidenceManifestId, "rawmanifest"),
    (TransformationId, "transformation"),
    (DatasetId, "dataset"),
    (AnalysisDefinitionId, "analysisdef"),
    (AnalysisResultId, "analysisresult"),
    (RequestId, "request"),
)


class EntityIdentifierTests(unittest.TestCase):
    def test_all_approved_types_generate_and_round_trip(self) -> None:
        for identifier_type, prefix in IDENTIFIER_TYPES:
            with self.subTest(identifier_type=identifier_type.__name__):
                identifier = new_entity_id(identifier_type)

                self.assertIs(type(identifier), identifier_type)
                self.assertTrue(str(identifier).startswith(f"{prefix}_"))
                self.assertEqual(identifier_type.parse(str(identifier)), identifier)

    def test_cross_type_and_wrong_prefix_are_rejected(self) -> None:
        run_id = new_entity_id(RunId)

        with self.assertRaises(InvalidIdentifierError):
            ArtifactId.parse(str(run_id))
        with self.assertRaises(InvalidIdentifierError):
            RunId.parse(str(run_id).replace("run_", "other_", 1))

    def test_non_uuid7_and_wrong_variant_are_rejected(self) -> None:
        with self.assertRaises(InvalidIdentifierError):
            RunId(f"run_{uuid4()}")

        uuid_text = str(uuid7())
        wrong_variant = f"{uuid_text[:19]}0{uuid_text[20:]}"
        with self.assertRaises(InvalidIdentifierError):
            RunId(f"run_{wrong_variant}")

    def test_noncanonical_uuid_text_is_rejected(self) -> None:
        uuid_text = str(uuid7())
        invalid_values = (
            f"run_{uuid_text.upper()}",
            f"run_{uuid_text.replace('-', '')}",
            f" run_{uuid_text}",
            f"run_{uuid_text} ",
            "",
        )

        for value in invalid_values:
            with self.subTest(value=value), self.assertRaises(
                InvalidIdentifierError
            ):
                RunId(value)

    def test_identifier_is_frozen_and_exposes_no_temporal_api(self) -> None:
        identifier = new_entity_id(RunId)

        with self.assertRaises(FrozenInstanceError):
            identifier.value = str(identifier)
        self.assertFalse(hasattr(identifier, "time"))
        self.assertFalse(hasattr(identifier, "timestamp"))
        self.assertFalse(hasattr(identifier, "uuid"))

    def test_generator_requires_a_concrete_identifier_type(self) -> None:
        with self.assertRaises(TypeError):
            new_entity_id(EntityId)


if __name__ == "__main__":
    unittest.main()
