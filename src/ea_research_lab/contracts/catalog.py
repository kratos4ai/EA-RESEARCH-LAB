"""Closed, repository-local catalog for exact schema identities."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Mapping

from referencing import Registry, Resource

from ea_research_lab.domain.values import SchemaName, SchemaRef, SchemaVersion


SCHEMA_ROOT = Path(__file__).resolve().parents[3] / "schemas"


def _ref(name: str, version: str) -> SchemaRef:
    return SchemaRef(SchemaName(name), SchemaVersion.parse(version))


SUPPORTED_SCHEMA_PATHS: Mapping[SchemaRef, Path] = MappingProxyType(
    {
        _ref("common", "1.0.0"): Path("common/v1.0.0.schema.json"),
        _ref("build-input-manifest", "0.1.0"): Path(
            "build-input-manifest/v0.1.0.schema.json"
        ),
        _ref("build-record", "0.1.0"): Path("build-record/v0.1.0.schema.json"),
        _ref("build-record", "0.2.0"): Path("build-record/v0.2.0.schema.json"),
        _ref("artifact-manifest", "0.1.0"): Path(
            "artifact-manifest/v0.1.0.schema.json"
        ),
        _ref("test-definition", "0.1.0"): Path(
            "test-definition/v0.1.0.schema.json"
        ),
        _ref("run-manifest", "0.1.0"): Path("run-manifest/v0.1.0.schema.json"),
        _ref("raw-evidence-manifest", "0.1.0"): Path(
            "raw-evidence-manifest/v0.1.0.schema.json"
        ),
        _ref("dataset-manifest", "0.1.0"): Path(
            "dataset-manifest/v0.1.0.schema.json"
        ),
        _ref("dataset-manifest", "0.2.0"): Path(
            "dataset-manifest/v0.2.0.schema.json"
        ),
        _ref("execution-summary", "0.1.0"): Path(
            "execution-summary/v0.1.0.schema.json"
        ),
        _ref("realized-execution-event-series", "0.1.0"): Path(
            "realized-execution-event-series/v0.1.0.schema.json"
        ),
        _ref("account-balance-event-series", "0.1.0"): Path(
            "account-balance-event-series/v0.1.0.schema.json"
        ),
        _ref("telemetry-envelope", "0.1.0"): Path(
            "telemetry-envelope/v0.1.0.schema.json"
        ),
        _ref("analysis-result", "0.1.0"): Path(
            "analysis-result/v0.1.0.schema.json"
        ),
        _ref("analysis-result", "0.2.0"): Path(
            "analysis-result/v0.2.0.schema.json"
        ),
        _ref("execution-summary-analysis-parameters", "0.1.0"): Path(
            "execution-summary-analysis-parameters/v0.1.0.schema.json"
        ),
        _ref("execution-summary-analysis-result", "0.1.0"): Path(
            "execution-summary-analysis-result/v0.1.0.schema.json"
        ),
        _ref("execution-core-analysis-parameters", "0.1.0"): Path(
            "execution-core-analysis-parameters/v0.1.0.schema.json"
        ),
        _ref("execution-core-analysis-result", "0.1.0"): Path(
            "execution-core-analysis-result/v0.1.0.schema.json"
        ),
        _ref("metaeditor-build-configuration", "0.1.0"): Path(
            "metaeditor-build-configuration/v0.1.0.schema.json"
        ),
        _ref("metaeditor-build-configuration", "0.2.0"): Path(
            "metaeditor-build-configuration/v0.2.0.schema.json"
        ),
        _ref("metaeditor-build-evidence", "0.1.0"): Path(
            "metaeditor-build-evidence/v0.1.0.schema.json"
        ),
        _ref("mt5-strategy-tester-configuration", "0.1.0"): Path(
            "mt5-strategy-tester-configuration/v0.1.0.schema.json"
        ),
        _ref("mt5-strategy-tester-configuration", "0.2.0"): Path(
            "mt5-strategy-tester-configuration/v0.2.0.schema.json"
        ),
        _ref("mt5-strategy-tester-execution", "0.1.0"): Path(
            "mt5-strategy-tester-execution/v0.1.0.schema.json"
        ),
        _ref("mt5-strategy-tester-evidence", "0.1.0"): Path(
            "mt5-strategy-tester-evidence/v0.1.0.schema.json"
        ),
    }
)


@dataclass(frozen=True, slots=True)
class SchemaCatalog:
    """In-memory schemas and a resolver with no retrieval callback."""

    schemas: Mapping[SchemaRef, Mapping[str, object]]
    registry: Registry

    def get(self, schema_ref: SchemaRef) -> Mapping[str, object] | None:
        return self.schemas.get(schema_ref)


def load_catalog(schema_root: Path = SCHEMA_ROOT) -> SchemaCatalog:
    """Load only the exact schema files declared by the local catalog."""

    schemas: dict[SchemaRef, Mapping[str, object]] = {}
    registry = Registry()

    for schema_ref, relative_path in SUPPORTED_SCHEMA_PATHS.items():
        path = schema_root / relative_path
        with path.open(encoding="utf-8") as stream:
            schema = json.load(stream)
        if not isinstance(schema, dict) or schema.get("$id") != str(schema_ref):
            raise ValueError(f"Schema identity does not match catalog entry: {path}")
        schemas[schema_ref] = schema
        registry = registry.with_resource(
            str(schema_ref), Resource.from_contents(schema)
        )

    return SchemaCatalog(MappingProxyType(schemas), registry)
