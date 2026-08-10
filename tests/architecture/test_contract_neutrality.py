"""Enforce the published contract set and opaque boundaries."""

from __future__ import annotations

import unittest
from pathlib import Path

from ea_research_lab.contracts.catalog import (
    SCHEMA_ROOT,
    SUPPORTED_SCHEMA_PATHS,
    load_catalog,
)


COMMON_ID = "urn:ea-research-lab:schema:common:1.0.0"
EXPECTED_PROPERTIES = {
    ("analysis-result", "0.1.0"): {
        "schema_name",
        "schema_version",
        "analysis_result_id",
        "created_at",
        "provenance",
        "result_schema",
        "result",
    },
    ("artifact-manifest", "0.1.0"): {
        "schema_name",
        "schema_version",
        "artifact_id",
        "logical_name",
        "artifact_version",
        "build_record_id",
        "source_revision",
        "binary_digest",
        "compiler",
        "built_at",
    },
    ("build-input-manifest", "0.1.0"): {
        "schema_name",
        "schema_version",
        "build_input_identity",
        "primary",
        "dependencies",
    },
    ("build-record", "0.1.0"): {
        "schema_name",
        "schema_version",
        "build_record_id",
        "source_revision",
        "build_configuration_id",
        "build_configuration",
        "status",
        "artifact_id",
    },
    ("build-record", "0.2.0"): {
        "schema_name",
        "schema_version",
        "build_record_id",
        "source_revision",
        "build_input",
        "build_configuration_id",
        "build_configuration",
        "provider_evidence",
        "status",
        "artifact_id",
    },
    ("dataset-manifest", "0.1.0"): {
        "schema_name",
        "schema_version",
        "dataset_id",
        "input_manifests",
        "input_datasets",
        "transformation_id",
        "transformation_version",
        "transformation_parameters",
        "created_at",
        "dataset_schema",
    },
    ("raw-evidence-manifest", "0.1.0"): {
        "schema_name",
        "schema_version",
        "manifest_id",
        "run_id",
        "objects",
        "sealed_at",
        "outcome",
        "prior_manifest",
    },
    ("run-manifest", "0.1.0"): {
        "schema_name",
        "schema_version",
        "run_id",
        "test_definition_revision_id",
        "artifact_id",
        "environment_configuration_id",
        "environment_configuration",
        "status",
        "created_at",
        "started_at",
        "finished_at",
        "execution_reproducibility",
        "raw_evidence_manifest",
    },
    ("telemetry-envelope", "0.1.0"): {
        "schema_name",
        "schema_version",
        "run_id",
        "stream_id",
        "sequence",
        "timestamp",
        "producer_namespace",
        "event_type",
        "payload_schema",
        "payload",
    },
    ("test-definition", "0.1.0"): {
        "schema_name",
        "schema_version",
        "test_definition_id",
        "test_definition_revision_id",
        "artifact_id",
        "execution_configuration",
        "sut_inputs",
    },
    ("metaeditor-build-configuration", "0.1.0"): {
        "schema_name",
        "schema_version",
        "provider",
        "executable_path",
        "executable_digest",
        "environment",
        "max_log_bytes",
    },
    ("metaeditor-build-configuration", "0.2.0"): {
        "schema_name",
        "schema_version",
        "provider",
        "executable_path",
        "executable_digest",
        "environment",
        "external_roots",
        "max_log_bytes",
    },
    ("metaeditor-build-evidence", "0.1.0"): {
        "schema_name",
        "schema_version",
        "provider",
        "executable_digest",
        "executable_version",
        "process_started",
        "timed_out",
        "exit_code",
        "duration_ms",
        "log_encoding",
        "log_digest",
        "compiler_verdict",
        "error_count",
        "warning_count",
        "candidate_observed",
        "declared_inputs_only",
    },
}
EXPECTED_COMMON_DEFINITIONS = {
    "analysis_definition_id",
    "analysis_result_id",
    "artifact_id",
    "build_record_id",
    "dataset_id",
    "environment_configuration_id",
    "raw_evidence_manifest_id",
    "raw_evidence_object_id",
    "reproducibility_assessment",
    "reproducibility_reason",
    "request_id",
    "run_id",
    "schema_ref",
    "sha256_digest",
    "test_definition_id",
    "test_definition_revision_id",
    "transformation_id",
    "utc_timestamp",
}


class ContractNeutralityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = load_catalog()
        cls.schemas = {
            (str(reference.name), str(reference.version)): schema
            for reference, schema in cls.catalog.schemas.items()
        }

    def test_catalog_and_filesystem_contain_the_same_published_schemas(self) -> None:
        files = {
            path.relative_to(SCHEMA_ROOT)
            for path in SCHEMA_ROOT.glob("*/*.schema.json")
        }
        self.assertEqual(files, set(SUPPORTED_SCHEMA_PATHS.values()))

    def test_schema_path_identity_and_discriminators_match_exactly(self) -> None:
        for reference, relative_path in SUPPORTED_SCHEMA_PATHS.items():
            schema = self.catalog.schemas[reference]
            with self.subTest(schema=str(reference)):
                self.assertEqual(
                    relative_path,
                    Path(str(reference.name)) / f"v{reference.version}.schema.json",
                )
                self.assertEqual(schema["$id"], str(reference))
                self.assertEqual(
                    schema["$schema"],
                    "https://json-schema.org/draft/2020-12/schema",
                )
                if str(reference.name) != "common":
                    self.assertEqual(
                        schema["properties"]["schema_name"]["const"],
                        str(reference.name),
                    )
                    self.assertEqual(
                        schema["properties"]["schema_version"]["const"],
                        str(reference.version),
                    )

    def test_core_contract_vocabulary_is_the_approved_neutral_set(self) -> None:
        self.assertEqual(
            set(self.schemas[("common", "1.0.0")]["$defs"]),
            EXPECTED_COMMON_DEFINITIONS,
        )
        for identity, expected in EXPECTED_PROPERTIES.items():
            schema = self.schemas[identity]
            with self.subTest(schema=identity):
                self.assertFalse(schema["additionalProperties"])
                self.assertEqual(set(schema["properties"]), expected)

    def test_opaque_extension_points_remain_schema_referenced(self) -> None:
        for identity in (
            ("analysis-result", "0.1.0"),
            ("build-record", "0.1.0"),
            ("build-record", "0.2.0"),
            ("dataset-manifest", "0.1.0"),
            ("run-manifest", "0.1.0"),
            ("test-definition", "0.1.0"),
        ):
            with self.subTest(schema=identity):
                self._assert_opaque_payload(
                    self.schemas[identity]["$defs"]["schema_referenced_payload"]
                )

        build_v2 = self.schemas[("build-record", "0.2.0")]
        self.assertEqual(
            build_v2["properties"]["provider_evidence"]["$ref"],
            "#/$defs/schema_referenced_payload",
        )

        compiler = self.schemas[("artifact-manifest", "0.1.0")]["$defs"][
            "namespaced_payload"
        ]
        self.assertEqual(
            set(compiler["required"]),
            {"namespace", "schema_ref", "value"},
        )
        self._assert_opaque_payload(compiler, namespaced=True)

        telemetry = self.schemas[("telemetry-envelope", "0.1.0")]["properties"]
        self._assert_schema_ref(telemetry["payload_schema"])
        self.assertTrue(telemetry["payload"]["additionalProperties"])

        analysis = self.schemas[("analysis-result", "0.1.0")]["properties"]
        self._assert_schema_ref(analysis["result_schema"])
        self.assertTrue(analysis["result"]["additionalProperties"])

        evidence_object = self.schemas[("raw-evidence-manifest", "0.1.0")][
            "$defs"
        ]["evidence_object"]
        self._assert_schema_ref(evidence_object["properties"]["payload_schema"])
        self.assertNotIn("payload", evidence_object["properties"])

    def test_metaeditor_contracts_remain_provider_namespaced(self) -> None:
        for identity in (
            ("metaeditor-build-configuration", "0.1.0"),
            ("metaeditor-build-configuration", "0.2.0"),
            ("metaeditor-build-evidence", "0.1.0"),
        ):
            with self.subTest(schema=identity):
                self.assertTrue(identity[0].startswith("metaeditor-"))
                self.assertEqual(
                    self.schemas[identity]["properties"]["provider"]["const"],
                    "metaeditor",
                )

    def _assert_opaque_payload(
        self,
        definition: dict[str, object],
        *,
        namespaced: bool = False,
    ) -> None:
        self.assertFalse(definition["additionalProperties"])
        required = {"schema_ref", "value"}
        if namespaced:
            required.add("namespace")
        self.assertEqual(set(definition["required"]), required)
        properties = definition["properties"]
        self._assert_schema_ref(properties["schema_ref"])
        self.assertEqual(properties["value"]["type"], "object")
        self.assertTrue(properties["value"]["additionalProperties"])

    def _assert_schema_ref(self, definition: dict[str, object]) -> None:
        self.assertEqual(
            definition["$ref"],
            f"{COMMON_ID}#/$defs/schema_ref",
        )


if __name__ == "__main__":
    unittest.main()
