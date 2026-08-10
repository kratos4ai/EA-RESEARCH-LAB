from __future__ import annotations

import hashlib
import os
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path

from ea_research_lab.application.build import (
    BuildRequest,
    BuildSourceInput,
    BuildSourceSpecification,
)
from ea_research_lab.application.context import RequestContext
from ea_research_lab.application.errors import ApplicationErrorCode
from ea_research_lab.application.identity import new_entity_id
from ea_research_lab.contracts import validate_document
from ea_research_lab.domain.build import BuildInputScope
from ea_research_lab.domain.identifiers import (
    BuildRecordId,
    EnvironmentConfigurationId,
    RequestId,
)
from ea_research_lab.domain.provenance import SchemaReferencedPayload
from ea_research_lab.domain.values import (
    SchemaName,
    SchemaRef,
    SchemaVersion,
    SourceRevision,
)
from ea_research_lab.infrastructure.build_workspace import (
    BuildWorkspaceError,
    load_source_input,
    materialize_build_workspace,
)


def _payload() -> SchemaReferencedPayload:
    return SchemaReferencedPayload(
        SchemaRef(SchemaName("build-configuration"), SchemaVersion(0, 1, 0)),
        {"opaque": "configuration"},
    )


def _request(specification: BuildSourceSpecification) -> BuildRequest:
    return BuildRequest(
        context=RequestContext(new_entity_id(RequestId), "test-client"),
        build_record_id=new_entity_id(BuildRecordId),
        source_revision=SourceRevision("git", "repository", "revision", True),
        source_specification=specification,
        build_configuration_id=new_entity_id(EnvironmentConfigurationId),
        build_configuration=_payload(),
        timeout=timedelta(seconds=30),
    )


def _workspace_source(path: str, content: bytes) -> BuildSourceInput:
    return BuildSourceInput(BuildInputScope.WORKSPACE, path, content)


class BuildWorkspaceTests(unittest.TestCase):
    def test_each_build_uses_a_new_exclusive_workspace_and_cleans_it(self) -> None:
        specification = BuildSourceSpecification(
            _workspace_source("Experts/Main.mq5", b"primary\n")
        )
        with tempfile.TemporaryDirectory() as parent_name:
            parent = Path(parent_name)
            with materialize_build_workspace(
                _request(specification), parent
            ) as first:
                first_root = first.root
                self.assertTrue(first_root.is_dir())
                with materialize_build_workspace(
                    _request(specification), parent
                ) as second:
                    self.assertNotEqual(first.root, second.root)
                    self.assertTrue(second.root.is_dir())
            self.assertFalse(first_root.exists())
            self.assertEqual(list(parent.iterdir()), [])

    def test_loaded_source_bytes_are_copied_not_read_from_development_tree(self) -> None:
        with tempfile.TemporaryDirectory() as parent_name:
            parent = Path(parent_name)
            source_path = parent / "development.mq5"
            source_path.write_bytes(b"original\r\n")
            source = load_source_input(
                scope=BuildInputScope.WORKSPACE,
                path="Experts/Main.mq5",
                source_path=source_path,
            )
            source_path.write_bytes(b"changed\n")

            with materialize_build_workspace(
                _request(BuildSourceSpecification(source)), parent
            ) as workspace:
                member = workspace.members[0]
                self.assertNotEqual(member.physical_path, source_path)
                self.assertEqual(member.physical_path.read_bytes(), b"original\r\n")
                self.assertEqual(
                    str(member.content_digest),
                    hashlib.sha256(b"original\r\n").hexdigest(),
                )

    def test_member_and_aggregate_identity_use_materialized_exact_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as parent_name:
            parent = Path(parent_name)
            first = BuildSourceSpecification(
                _workspace_source("Experts/Main.mq5", b"content\n")
            )
            second = BuildSourceSpecification(
                _workspace_source("Experts/Main.mq5", b"content\r\n")
            )
            with materialize_build_workspace(_request(first), parent) as workspace:
                first_member = str(workspace.members[0].content_digest)
                first_identity = workspace.manifest["build_input_identity"]
            with materialize_build_workspace(_request(second), parent) as workspace:
                second_member = str(workspace.members[0].content_digest)
                second_identity = workspace.manifest["build_input_identity"]

            self.assertNotEqual(first_member, second_member)
            self.assertNotEqual(first_identity, second_identity)

    def test_workspace_and_external_dependencies_are_materialized(self) -> None:
        specification = BuildSourceSpecification(
            primary=_workspace_source("Experts/Main.mq5", b"primary\n"),
            dependencies=(
                _workspace_source("Include/Local.mqh", b"local\n"),
                BuildSourceInput(
                    BuildInputScope.EXTERNAL,
                    "Arrays/Array.mqh",
                    b"external\n",
                    root="mql5-standard",
                ),
            ),
        )
        with tempfile.TemporaryDirectory() as parent_name:
            with materialize_build_workspace(
                _request(specification), Path(parent_name)
            ) as workspace:
                self.assertEqual(len(workspace.members), 3)
                self.assertEqual(
                    workspace.members[1].physical_path.read_bytes(), b"local\n"
                )
                self.assertEqual(
                    workspace.members[2].physical_path.read_bytes(), b"external\n"
                )
                self.assertEqual(
                    workspace.external_roots["mql5-standard"],
                    workspace.root / "external" / "mql5-standard",
                )
                validate_document(workspace.manifest)
                workspace.verify_integrity()

    def test_external_identity_is_independent_from_original_physical_path(self) -> None:
        with tempfile.TemporaryDirectory() as parent_name:
            parent = Path(parent_name)
            first_path = parent / "machine-a" / "dependency.mqh"
            second_path = parent / "machine-b" / "dependency.mqh"
            first_path.parent.mkdir()
            second_path.parent.mkdir()
            first_path.write_bytes(b"same exact bytes\n")
            second_path.write_bytes(b"same exact bytes\n")

            identities = []
            for source_path in (first_path, second_path):
                external = load_source_input(
                    scope=BuildInputScope.EXTERNAL,
                    root="mql5-standard",
                    path="Arrays/Dependency.mqh",
                    source_path=source_path,
                )
                specification = BuildSourceSpecification(
                    _workspace_source("Experts/Main.mq5", b"primary\n"),
                    (external,),
                )
                with materialize_build_workspace(
                    _request(specification), parent
                ) as workspace:
                    identities.append(workspace.manifest["build_input_identity"])
                    self.assertNotIn(
                        str(source_path), repr(workspace.manifest)
                    )

            self.assertEqual(identities[0], identities[1])

    def test_invalid_and_colliding_logical_targets_are_rejected(self) -> None:
        invalid_dependencies = (
            (_workspace_source("../escape.mqh", b"escape"),),
            (_workspace_source("/absolute.mqh", b"absolute"),),
            (_workspace_source("C:/absolute.mqh", b"absolute"),),
            (
                _workspace_source("Include/Same.mqh", b"first"),
                _workspace_source("Include/Same.mqh", b"second"),
            ),
            (
                _workspace_source("Include/Café.mqh", b"first"),
                _workspace_source("Include/Café.mqh", b"second"),
            ),
        )
        with tempfile.TemporaryDirectory() as parent_name:
            parent = Path(parent_name)
            for dependencies in invalid_dependencies:
                specification = BuildSourceSpecification(
                    _workspace_source("Experts/Main.mq5", b"primary\n"),
                    dependencies,
                )
                with self.subTest(dependencies=dependencies), self.assertRaises(
                    BuildWorkspaceError
                ):
                    with materialize_build_workspace(
                        _request(specification), parent
                    ):
                        pass

    def test_integrity_verification_detects_snapshot_modification(self) -> None:
        specification = BuildSourceSpecification(
            _workspace_source("Experts/Main.mq5", b"primary\n")
        )
        with tempfile.TemporaryDirectory() as parent_name:
            with materialize_build_workspace(
                _request(specification), Path(parent_name)
            ) as workspace:
                workspace.verify_integrity()
                workspace.members[0].physical_path.write_bytes(b"modified\n")
                with self.assertRaises(BuildWorkspaceError):
                    workspace.verify_integrity()

    def test_unsafe_or_missing_physical_sources_fail_without_path_disclosure(self) -> None:
        with tempfile.TemporaryDirectory() as parent_name:
            missing = Path(parent_name) / "sensitive-source.mq5"
            with self.assertRaises(BuildWorkspaceError) as caught:
                load_source_input(
                    scope=BuildInputScope.WORKSPACE,
                    path="Experts/Main.mq5",
                    source_path=missing,
                )
            self.assertEqual(
                caught.exception.code,
                ApplicationErrorCode.BUILD_INPUT_INVALID.value,
            )
            self.assertNotIn(str(missing), str(caught.exception))

            if hasattr(os, "symlink"):
                target = Path(parent_name) / "target.mq5"
                link = Path(parent_name) / "link.mq5"
                target.write_bytes(b"source\n")
                try:
                    link.symlink_to(target)
                except OSError:
                    return
                with self.assertRaises(BuildWorkspaceError):
                    load_source_input(
                        scope=BuildInputScope.WORKSPACE,
                        path="Experts/Main.mq5",
                        source_path=link,
                    )


if __name__ == "__main__":
    unittest.main()
