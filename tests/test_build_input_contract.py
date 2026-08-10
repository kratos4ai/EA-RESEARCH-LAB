from __future__ import annotations

import copy
import hashlib
import json
import unittest
from pathlib import Path

from ea_research_lab.contracts import (
    ContractValidationError,
    calculate_build_input_identity,
    normalize_logical_path,
    validate_document,
)


VALID_FIXTURES = Path(__file__).parent / "fixtures" / "schemas" / "valid"


def _digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _member(
    scope: str,
    path: str,
    content: bytes,
    *,
    root: str | None = None,
) -> dict[str, object]:
    location: dict[str, object] = {"scope": scope, "path": path}
    if root is not None:
        location["root"] = root
    return {"logical_location": location, "content_digest": _digest(content)}


def _manifest(
    primary: dict[str, object], dependencies: list[dict[str, object]]
) -> dict[str, object]:
    return {
        "schema_name": "build-input-manifest",
        "schema_version": "0.1.0",
        "build_input_identity": str(
            calculate_build_input_identity(primary, dependencies)
        ),
        "primary": primary,
        "dependencies": dependencies,
    }


def _fixture(name: str) -> dict[str, object]:
    with (VALID_FIXTURES / name).open(encoding="utf-8") as stream:
        return json.load(stream)


class BuildInputIdentityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.primary = _member(
            "workspace", "Experts/Main.mq5", b"primary\n"
        )

    def test_valid_primary_workspace_and_external_inputs(self) -> None:
        manifests = (
            _manifest(self.primary, []),
            _manifest(
                self.primary,
                [_member("workspace", "Include/Local.mqh", b"local\n")],
            ),
            _manifest(
                self.primary,
                [
                    _member(
                        "external",
                        "Arrays/Array.mqh",
                        b"external\n",
                        root="mql5-standard",
                    )
                ],
            ),
        )
        for manifest in manifests:
            with self.subTest(dependencies=manifest["dependencies"]):
                validate_document(manifest)

    def test_exact_source_bytes_determine_member_and_aggregate_identity(self) -> None:
        unix = _member("workspace", "Include/Bytes.mqh", b"same text\n")
        windows = _member("workspace", "Include/Bytes.mqh", b"same text\r\n")

        self.assertNotEqual(unix["content_digest"], windows["content_digest"])
        self.assertNotEqual(
            calculate_build_input_identity(self.primary, [unix]),
            calculate_build_input_identity(self.primary, [windows]),
        )

    def test_json_formatting_and_dependency_order_do_not_change_identity(self) -> None:
        dependency_a = _member("workspace", "Include/A.mqh", b"a\n")
        dependency_b = _member(
            "external", "Core/B.mqh", b"b\n", root="vendor-sdk"
        )
        compact = json.loads(
            json.dumps(
                {"primary": self.primary, "dependencies": [dependency_a, dependency_b]},
                separators=(",", ":"),
            )
        )
        formatted = json.loads(
            json.dumps(
                {"dependencies": [dependency_b, dependency_a], "primary": self.primary},
                indent=4,
                sort_keys=True,
            )
        )

        self.assertEqual(
            calculate_build_input_identity(
                compact["primary"], compact["dependencies"]
            ),
            calculate_build_input_identity(
                formatted["primary"], formatted["dependencies"]
            ),
        )

    def test_logical_location_participates_in_identity(self) -> None:
        first = _member("workspace", "Include/A.mqh", b"same\n")
        second = _member("workspace", "Include/B.mqh", b"same\n")
        self.assertNotEqual(
            calculate_build_input_identity(self.primary, [first]),
            calculate_build_input_identity(self.primary, [second]),
        )

    def test_unicode_paths_use_nfc(self) -> None:
        decomposed = "Experts/Cafe\u0301.mq5"
        composed = "Experts/Café.mq5"
        self.assertEqual(normalize_logical_path(decomposed), composed)
        self.assertEqual(
            calculate_build_input_identity(
                _member("workspace", decomposed, b"unicode\n"), []
            ),
            calculate_build_input_identity(
                _member("workspace", composed, b"unicode\n"), []
            ),
        )

        invalid_wire_document = _manifest(
            _member("workspace", decomposed, b"unicode\n"), []
        )
        with self.assertRaises(ContractValidationError):
            validate_document(invalid_wire_document)

    def test_invalid_logical_paths_are_rejected(self) -> None:
        invalid_paths = (
            "/absolute/file.mq5",
            "relative/file.mq5/",
            "relative//file.mq5",
            "relative/./file.mq5",
            "relative/../file.mq5",
            "C:/physical/file.mq5",
            "C:physical/file.mq5",
            "\\\\server\\share\\file.mq5",
            "file:///physical/file.mq5",
            "relative\\file.mq5",
            "relative/\n/file.mq5",
        )
        for path in invalid_paths:
            with self.subTest(path=path), self.assertRaises(
                ContractValidationError
            ):
                normalize_logical_path(path)

    def test_duplicate_and_normalization_collisions_are_rejected(self) -> None:
        same = _member("workspace", "Include/Café.mqh", b"same\n")
        conflicting = _member("workspace", "Include/Café.mqh", b"other\n")
        decomposed = _member("workspace", "Include/Cafe\u0301.mqh", b"same\n")
        for dependencies in (
            [same, copy.deepcopy(same)],
            [same, conflicting],
            [same, decomposed],
            [copy.deepcopy(self.primary)],
        ):
            with self.subTest(dependencies=dependencies), self.assertRaises(
                ContractValidationError
            ):
                calculate_build_input_identity(self.primary, dependencies)

    def test_same_digest_at_different_locations_is_valid(self) -> None:
        first = _member("workspace", "Include/A.mqh", b"same\n")
        second = _member("workspace", "Include/B.mqh", b"same\n")
        manifest = _manifest(self.primary, [first, second])
        validate_document(manifest)

    def test_fixed_identity_vectors(self) -> None:
        vectors = (
            (
                self.primary,
                [],
                "919c85ac288400dffdd48734e109476b6a75155f44ae4d96e0d4f97c28e78b6c",
            ),
            (
                self.primary,
                [
                    _member(
                        "workspace",
                        "Include/Local.mqh",
                        b"workspace dependency\n",
                    )
                ],
                "1b28c6f433c6397f0b9702ffe169ccf75fbfe4e628668258e3a6ff53ba8b3377",
            ),
            (
                self.primary,
                [
                    _member(
                        "external",
                        "Arrays/Array.mqh",
                        b"external dependency\n",
                        root="mql5-standard",
                    )
                ],
                "c497389feadb48c8109aeab026562d1830a3e3000c620ab5ed2c4adfd959c227",
            ),
            (
                self.primary,
                [
                    _member(
                        "external", "Core/Zeta.mqh", b"zeta\n", root="vendor-sdk"
                    ),
                    _member("workspace", "Include/Beta.mqh", b"beta\n"),
                    _member("workspace", "Include/Alpha.mqh", b"alpha\n"),
                ],
                "ff8ced4dbd5bc93458249da6097bee6ba4611bccfff0504c9422986684b64dfd",
            ),
            (
                _member("workspace", "Experts/Cafe\u0301.mq5", b"unicode\n"),
                [],
                "79e1d69da99f229d056c9f45a8e0b1f2764d9fcc2176a66f2a1356993e010569",
            ),
        )
        for primary, dependencies, expected in vectors:
            with self.subTest(expected=expected):
                self.assertEqual(
                    str(calculate_build_input_identity(primary, dependencies)),
                    expected,
                )


class BuildInputContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.manifest = _fixture("build-input-manifest.json")
        self.build_v1 = _fixture("build-record.json")
        self.build_v2 = _fixture("build-record-v0.2.0.json")

    def test_manifest_rejects_invalid_primary_and_root_shapes(self) -> None:
        cases = []

        external_primary = copy.deepcopy(self.manifest)
        external_primary["primary"]["logical_location"] = {
            "scope": "external",
            "root": "source-root",
            "path": "Experts/Main.mq5",
        }
        cases.append(external_primary)

        missing_external_root = copy.deepcopy(self.manifest)
        del missing_external_root["dependencies"][1]["logical_location"]["root"]
        cases.append(missing_external_root)

        workspace_root = copy.deepcopy(self.manifest)
        workspace_root["dependencies"][0]["logical_location"]["root"] = "local"
        cases.append(workspace_root)

        missing_primary = copy.deepcopy(self.manifest)
        del missing_primary["primary"]
        cases.append(missing_primary)

        for document in cases:
            with self.subTest(document=document), self.assertRaises(
                ContractValidationError
            ):
                validate_document(document)

    def test_manifest_rejects_incorrect_declared_identity(self) -> None:
        invalid = copy.deepcopy(self.manifest)
        invalid["build_input_identity"] = "0" * 64
        with self.assertRaises(ContractValidationError) as caught:
            validate_document(invalid)
        self.assertEqual(caught.exception.path, "$.build_input_identity")

    def test_manifest_excludes_provenance_environment_and_physical_paths(self) -> None:
        for field in (
            "source_revision",
            "build_environment",
            "physical_path",
            "provider_evidence",
        ):
            invalid = copy.deepcopy(self.manifest)
            invalid[field] = {}
            with self.subTest(field=field), self.assertRaises(
                ContractValidationError
            ):
                validate_document(invalid)

    def test_build_record_exact_versions_remain_supported(self) -> None:
        validate_document(self.build_v1)
        validate_document(self.build_v2)

    def test_successful_build_v2_requires_artifact_and_build_input(self) -> None:
        for field in ("artifact_id", "build_input"):
            invalid = copy.deepcopy(self.build_v2)
            del invalid[field]
            with self.subTest(field=field), self.assertRaises(
                ContractValidationError
            ):
                validate_document(invalid)

    def test_failed_build_rejects_artifact_and_may_preserve_build_input(self) -> None:
        failed_with_input = copy.deepcopy(self.build_v2)
        failed_with_input["status"] = "failed"
        del failed_with_input["artifact_id"]
        validate_document(failed_with_input)

        failed_without_input = copy.deepcopy(failed_with_input)
        del failed_without_input["build_input"]
        validate_document(failed_without_input)

        failed_with_artifact = copy.deepcopy(failed_with_input)
        failed_with_artifact["artifact_id"] = self.build_v2["artifact_id"]
        with self.assertRaises(ContractValidationError):
            validate_document(failed_with_artifact)

    def test_provider_evidence_is_opaque_schema_referenced_data(self) -> None:
        without_evidence = copy.deepcopy(self.build_v2)
        del without_evidence["provider_evidence"]
        validate_document(without_evidence)

        extended = copy.deepcopy(self.build_v2)
        extended["provider_evidence"]["value"]["provider_native"] = {
            "exit_code": 1,
            "diagnostics": ["opaque"],
        }
        validate_document(extended)

        invalid = copy.deepcopy(self.build_v2)
        invalid["provider_exit_code"] = 1
        with self.assertRaises(ContractValidationError):
            validate_document(invalid)

    def test_build_record_rejects_wrong_input_contract_and_reproducibility(self) -> None:
        wrong_ref = copy.deepcopy(self.build_v2)
        wrong_ref["build_input"]["schema_ref"] = (
            "urn:ea-research-lab:schema:build-input-manifest:0.2.0"
        )
        with self.assertRaises(ContractValidationError):
            validate_document(wrong_ref)

        with_reproducibility = copy.deepcopy(self.build_v2)
        with_reproducibility["build_reproducibility"] = {
            "level": "exact",
            "reasons": [],
        }
        with self.assertRaises(ContractValidationError):
            validate_document(with_reproducibility)

    def test_artifact_manifest_remains_linked_only_through_build_record(self) -> None:
        artifact = _fixture("artifact-manifest.json")
        validate_document(artifact)
        self.assertNotIn("build_input", artifact)
        self.assertNotIn("build_input_identity", artifact)


if __name__ == "__main__":
    unittest.main()
