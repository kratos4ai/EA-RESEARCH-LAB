"""Contract tests for the exact local schema catalog."""

from __future__ import annotations

import copy
import hashlib
import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker
from referencing.exceptions import NoSuchResource

from ea_research_lab.contracts.catalog import (
    SCHEMA_ROOT,
    SUPPORTED_SCHEMA_PATHS,
    SchemaCatalog,
    load_catalog,
)
from ea_research_lab.contracts.validation import (
    ContractValidationError,
    build_validator,
    validate_document,
)
from ea_research_lab.domain.values import SchemaName, SchemaRef, SchemaVersion


FIXTURES = Path(__file__).parent / "fixtures" / "schemas"
VALID_FIXTURES = FIXTURES / "valid"
HISTORICAL_SCHEMA_DIGESTS = {
    Path("common/v1.0.0.schema.json"): "6467d1eb088e19a9ddf13db98ce2003854178dab93e392dd3e9b22a2ab4802da",
    Path("dataset-manifest/v0.1.0.schema.json"): "6686929429fe006c7ca5bd6a228c51ce71e207455bf3d1990df8f600a4f5213f",
    Path("analysis-result/v0.1.0.schema.json"): "da2fe6b78b39c17a59828fe0cd59574bb3e08118ad09b9081fc308310f71e73d",
    Path("realized-execution-event-series/v0.1.0.schema.json"): "49884c08cf97cb9bc6e0f3d2d8596eafd0d1a0720e01854f6bab28c307ed7500",
    Path("account-balance-event-series/v0.1.0.schema.json"): "69c3437b8cd3a5af377ddbdd3042f0157d4d70b9de55961b93dcdd179661b984",
    Path("execution-core-analysis-parameters/v0.1.0.schema.json"): "bab11ec600b218cb3745a2ab469e1e36cc93f14222eb26a717629a20cf59ffa4",
    Path("execution-core-analysis-result/v0.1.0.schema.json"): "a5da3130da0839ccd22946e699bc0b131010a0ca1e535a5d3ae31a74c574ab9b",
}


def _load_json(path: Path) -> object:
    with path.open(encoding="utf-8") as stream:
        return json.load(stream)


class ContractSchemaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = load_catalog()
        cls.valid_documents = {
            path.name: _load_json(path)
            for path in sorted(VALID_FIXTURES.glob("*.json"))
        }

    def test_catalog_contains_only_approved_exact_versions(self) -> None:
        actual = {(str(ref.name), str(ref.version)) for ref in self.catalog.schemas}
        self.assertEqual(
            actual,
            {
                ("common", "1.0.0"),
                ("build-input-manifest", "0.1.0"),
                ("build-record", "0.1.0"),
                ("build-record", "0.2.0"),
                ("artifact-manifest", "0.1.0"),
                ("test-definition", "0.1.0"),
                ("run-manifest", "0.1.0"),
                ("raw-evidence-manifest", "0.1.0"),
                ("dataset-manifest", "0.1.0"),
                ("dataset-manifest", "0.2.0"),
                ("execution-summary", "0.1.0"),
                ("realized-execution-event-series", "0.1.0"),
                ("account-balance-event-series", "0.1.0"),
                ("telemetry-envelope", "0.1.0"),
                ("analysis-result", "0.1.0"),
                ("analysis-result", "0.2.0"),
                ("execution-summary-analysis-parameters", "0.1.0"),
                ("execution-summary-analysis-result", "0.1.0"),
                ("execution-core-analysis-parameters", "0.1.0"),
                ("execution-core-analysis-result", "0.1.0"),
                ("metaeditor-build-configuration", "0.1.0"),
                ("metaeditor-build-configuration", "0.2.0"),
                ("metaeditor-build-evidence", "0.1.0"),
                ("mt5-strategy-tester-configuration", "0.1.0"),
                ("mt5-strategy-tester-configuration", "0.2.0"),
                ("mt5-strategy-tester-execution", "0.1.0"),
                ("mt5-strategy-tester-evidence", "0.1.0"),
            },
        )
        self.assertEqual(len(SUPPORTED_SCHEMA_PATHS), 27)

    def test_every_schema_is_valid_draft_2020_12(self) -> None:
        identifiers = set()
        for schema in self.catalog.schemas.values():
            Draft202012Validator.check_schema(schema)
            schema_id = schema["$id"]
            self.assertNotIn(schema_id, identifiers)
            identifiers.add(schema_id)

    def test_historical_contract_bytes_remain_unchanged(self) -> None:
        for relative_path, expected in HISTORICAL_SCHEMA_DIGESTS.items():
            with self.subTest(schema=relative_path):
                content = (SCHEMA_ROOT / relative_path).read_bytes()
                self.assertEqual(hashlib.sha256(content).hexdigest(), expected)

    def test_every_internal_reference_resolves_from_closed_catalog(self) -> None:
        for schema in self.catalog.schemas.values():
            for reference in self._references(schema):
                if reference.startswith("#"):
                    continue
                resource_id = reference.split("#", 1)[0]
                self.catalog.registry.contents(resource_id)

        with self.assertRaises(NoSuchResource):
            self.catalog.registry.get_or_retrieve(
                "https://example.invalid/network-resolution-is-forbidden"
            )

    def test_validator_explicitly_enables_required_formats(self) -> None:
        schema = next(iter(self.catalog.schemas.values()))
        validator = build_validator(schema, self.catalog)
        self.assertIsInstance(validator.format_checker, FormatChecker)
        for required_format in ("date-time", "uri"):
            self.assertIn(required_format, validator.format_checker.checkers)

    def test_invalid_declared_formats_are_rejected_by_format_checker(self) -> None:
        common = self.catalog.schemas[self._schema_ref("common", "1.0.0")]
        cases = (
            (common["$defs"]["utc_timestamp"], "2026-02-30T12:00:00Z"),
            (common["$defs"]["schema_ref"], "not a uri"),
        )
        for schema, invalid_value in cases:
            with self.subTest(format=schema["format"]):
                validator = build_validator(schema, self.catalog)
                errors = list(validator.iter_errors(invalid_value))
                self.assertIn("format", {error.validator for error in errors})

    def test_stable_common_identifier_definitions_enforce_prefix_and_uuidv7(self) -> None:
        common = self.catalog.schemas[self._schema_ref("common", "1.0.0")]
        identifiers = {
            "build_record_id": "build_0195395c-7c9e-7a91-8c2b-6d4f8e1a2b3c",
            "artifact_id": "artifact_0195395c-7c9e-7b12-9d3c-7e5f9a2b3c4d",
            "test_definition_id": "testdef_0195395c-7c9e-7c23-ae4d-8f6a0b3c4d5e",
            "test_definition_revision_id": "testrev_0195395c-7c9e-7d34-bf5e-9a7b1c3d5e6f",
            "environment_configuration_id": "envcfg_0195395c-7c9e-7e45-8a6f-1b3c5d7e9f01",
            "run_id": "run_0195395c-7c9e-7f56-9b70-2c4d6e8f0a12",
            "raw_evidence_object_id": "rawobj_0195395c-7c9e-7167-9b82-4e6f8a0b2c34",
            "raw_evidence_manifest_id": "rawmanifest_0195395c-7c9e-7056-8a71-3d5e7f9a1b23",
            "transformation_id": "transformation_0195395c-7c9e-7278-ac93-5f7a9b1c3d45",
            "dataset_id": "dataset_0195395c-7c9e-7389-bda4-6a8b0c2d4e56",
            "analysis_definition_id": "analysisdef_0195395c-7c9e-74ab-9fc6-8c0d2e4f6a78",
            "analysis_result_id": "analysisresult_0195395c-7c9e-749a-8eb5-7b9c1d3e5f67",
            "request_id": "request_0195395c-7c9e-75bc-8ad7-9d1e3f5a7b89",
        }
        for definition, value in identifiers.items():
            validator = build_validator(common["$defs"][definition], self.catalog)
            with self.subTest(definition=definition):
                self.assertFalse(list(validator.iter_errors(value)))
                self.assertTrue(
                    list(
                        validator.iter_errors(
                            value.rsplit("_", 1)[0]
                            + "_0195395c-7c9e-4a91-8c2b-6d4f8e1a2b3c"
                        )
                    )
                )

    def test_stable_common_reproducibility_values_match_domain_values(self) -> None:
        schema = {
            "$ref": (
                "urn:ea-research-lab:schema:common:1.0.0"
                "#/$defs/reproducibility_assessment"
            )
        }
        validator = build_validator(schema, self.catalog)
        for level in ("exact", "equivalent"):
            with self.subTest(level=level):
                self.assertFalse(
                    list(validator.iter_errors({"level": level, "reasons": []}))
                )
        for level in ("best_effort", "unavailable"):
            with self.subTest(level=level):
                assessment = {
                    "level": level,
                    "reasons": [
                        {"code": "provider_limit", "detail": "Recorded limitation."}
                    ],
                }
                self.assertFalse(list(validator.iter_errors(assessment)))
        self.assertTrue(
            list(validator.iter_errors({"level": "deterministic", "reasons": []}))
        )

    def test_all_representative_documents_validate(self) -> None:
        self.assertEqual(len(self.valid_documents), 26)
        for name, document in self.valid_documents.items():
            with self.subTest(fixture=name):
                validate_document(document, self.catalog)

    def test_each_boundary_contract_rejects_missing_discriminator(self) -> None:
        for name, document in self.valid_documents.items():
            invalid = copy.deepcopy(document)
            del invalid["schema_name"]
            with self.subTest(fixture=name):
                with self.assertRaises(ContractValidationError) as caught:
                    validate_document(invalid, self.catalog)
                self.assertEqual(caught.exception.code, "schema_validation_failed")
                self.assertEqual(caught.exception.path, "$.schema_name")

    def test_each_boundary_contract_rejects_missing_required_field(self) -> None:
        for name, document in self.valid_documents.items():
            invalid = copy.deepcopy(document)
            schema = self._schema_for(document)
            required_field = next(
                (
                    field
                    for field in schema["required"]
                    if field not in {"schema_name", "schema_version"}
                ),
                None,
            )
            if required_field is None:
                continue
            del invalid[required_field]
            with self.subTest(fixture=name, field=required_field):
                with self.assertRaises(ContractValidationError) as caught:
                    validate_document(invalid, self.catalog)
                self.assertEqual(caught.exception.code, "schema_validation_failed")

    def test_each_boundary_contract_rejects_unknown_exact_version(self) -> None:
        for name, document in self.valid_documents.items():
            invalid = copy.deepcopy(document)
            invalid["schema_version"] = "0.1.1"
            with self.subTest(fixture=name):
                with self.assertRaises(ContractValidationError) as caught:
                    validate_document(invalid, self.catalog)
                self.assertEqual(caught.exception.code, "unsupported_schema")
                self.assertEqual(caught.exception.path, "$.schema_version")

    def test_each_boundary_contract_rejects_unexpected_core_property(self) -> None:
        for name, document in self.valid_documents.items():
            invalid = copy.deepcopy(document)
            invalid["unexpected_core_property"] = True
            with self.subTest(fixture=name):
                with self.assertRaises(ContractValidationError) as caught:
                    validate_document(invalid, self.catalog)
                self.assertEqual(caught.exception.code, "schema_validation_failed")
                self.assertEqual(caught.exception.path, "$")

    def test_each_boundary_contract_rejects_wrong_primary_id_prefix(self) -> None:
        primary_ids = {
            "build-record.json": "build_record_id",
            "build-record-v0.2.0.json": "build_record_id",
            "artifact-manifest.json": "artifact_id",
            "test-definition.json": "test_definition_id",
            "run-manifest.json": "run_id",
            "raw-evidence-manifest.json": "manifest_id",
            "dataset-manifest.json": "dataset_id",
            "dataset-manifest-v0.2.0.json": "dataset_id",
            "telemetry-envelope.json": "run_id",
            "analysis-result.json": "analysis_result_id",
            "analysis-result-v0.2.0.json": "analysis_result_id",
        }
        for name, identifier_field in primary_ids.items():
            invalid = copy.deepcopy(self.valid_documents[name])
            invalid[identifier_field] = (
                "wrong_0195395c-7c9e-7a91-8c2b-6d4f8e1a2b3c"
            )
            with self.subTest(fixture=name, field=identifier_field):
                with self.assertRaises(ContractValidationError) as caught:
                    validate_document(invalid, self.catalog)
                self.assertEqual(caught.exception.code, "schema_validation_failed")
                self.assertEqual(caught.exception.path, f"$.{identifier_field}")

    def test_declared_negative_fixtures_fail_with_stable_code_and_path(self) -> None:
        cases = _load_json(FIXTURES / "invalid" / "cases.json")
        for case in cases:
            invalid = copy.deepcopy(self.valid_documents[case["base"]])
            self._mutate(invalid, case)
            with self.subTest(case=case["name"]):
                with self.assertRaises(ContractValidationError) as caught:
                    validate_document(invalid, self.catalog)
                self.assertEqual(caught.exception.code, case["expected_code"])
                self.assertEqual(caught.exception.path, case["expected_path"])

    def test_opaque_payloads_accept_external_semantics_only_inside_envelopes(self) -> None:
        test_definition = copy.deepcopy(
            self.valid_documents["test-definition.json"]
        )
        test_definition["sut_inputs"]["value"]["strategy_owned_signal"] = {
            "provider_native_shape": [1, 2, 3]
        }
        validate_document(test_definition, self.catalog)

        test_definition["strategy_owned_signal"] = True
        with self.assertRaises(ContractValidationError):
            validate_document(test_definition, self.catalog)

    def test_valid_fixtures_form_the_canonical_linked_chain(self) -> None:
        build = self.valid_documents["build-record.json"]
        artifact = self.valid_documents["artifact-manifest.json"]
        test_definition = self.valid_documents["test-definition.json"]
        run = self.valid_documents["run-manifest.json"]
        evidence = self.valid_documents["raw-evidence-manifest.json"]
        dataset = self.valid_documents["dataset-manifest-v0.2.0.json"]
        analysis = self.valid_documents["analysis-result-v0.2.0.json"]

        self.assertEqual(build["artifact_id"], artifact["artifact_id"])
        self.assertEqual(artifact["artifact_id"], test_definition["artifact_id"])
        self.assertEqual(
            test_definition["test_definition_revision_id"],
            run["test_definition_revision_id"],
        )
        self.assertEqual(run["run_id"], evidence["run_id"])
        self.assertEqual(
            run["raw_evidence_manifest"]["manifest_id"], evidence["manifest_id"]
        )
        self.assertEqual(
            evidence["prior_manifest"]["run_id"], evidence["run_id"]
        )
        self.assertEqual(
            dataset["input_manifests"][0], run["raw_evidence_manifest"]
        )
        self.assertIn(
            {
                "dataset_id": dataset["dataset_id"],
                "content_digest": dataset["content_digest"],
            },
            analysis["provenance"]["input_datasets"],
        )
        result_bytes = json.dumps(
            analysis["result"],
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        self.assertEqual(
            analysis["result_digest"], hashlib.sha256(result_bytes).hexdigest()
        )

    def _schema_for(self, document: dict[str, object]) -> dict[str, object]:
        schema_ref = self._schema_ref(
            document["schema_name"], document["schema_version"]
        )
        return self.catalog.schemas[schema_ref]

    @staticmethod
    def _schema_ref(name: str, version: str) -> SchemaRef:
        return SchemaRef(SchemaName(name), SchemaVersion.parse(version))

    @staticmethod
    def _references(value: object):
        if isinstance(value, dict):
            for key, child in value.items():
                if key == "$ref":
                    yield child
                else:
                    yield from ContractSchemaTests._references(child)
        elif isinstance(value, list):
            for child in value:
                yield from ContractSchemaTests._references(child)

    @staticmethod
    def _mutate(document: dict[str, object], case: dict[str, object]) -> None:
        target = document
        for part in case["path"][:-1]:
            target = target[part]
        key = case["path"][-1]
        if case["operation"] == "remove":
            del target[key]
        else:
            target[key] = case["value"]


if __name__ == "__main__":
    unittest.main()
