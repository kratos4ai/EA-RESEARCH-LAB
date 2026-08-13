from __future__ import annotations

import copy
import json
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path

from ea_research_lab.contracts import ContractValidationError
from ea_research_lab.domain.provenance import SchemaReferencedPayload
from ea_research_lab.domain.values import SchemaName, SchemaRef, SchemaVersion
from ea_research_lab.infrastructure.mt5_semantic import (
    Mt5ExperimentContextProjector,
)
from ea_research_lab.infrastructure.metaeditor_semantic import (
    MetaEditorBuildRuntimeProjector,
)
from tests.test_mt5_strategy_tester import _execution_document


MT5_EXECUTION_REF = SchemaRef(
    SchemaName("mt5-strategy-tester-execution"), SchemaVersion(0, 1, 0)
)
METAEDITOR_EVIDENCE_REF = SchemaRef(
    SchemaName("metaeditor-build-evidence"), SchemaVersion(0, 1, 0)
)
FIXTURES = Path(__file__).parent / "fixtures" / "schemas" / "valid"


class Mt5SemanticTests(unittest.TestCase):
    def test_exact_configuration_projects_only_supported_neutral_context(self) -> None:
        projection = Mt5ExperimentContextProjector().project(
            SchemaReferencedPayload(MT5_EXECUTION_REF, _execution_document())
        )

        self.assertEqual(projection.instrument, "EURUSD")
        self.assertEqual(projection.timeframe, "M1")
        self.assertEqual(projection.start_date, date(2026, 8, 3))
        self.assertEqual(projection.end_date, date(2026, 8, 4))
        self.assertEqual(projection.requested_initial_capital, Decimal("10000"))
        self.assertEqual(projection.currency, "USD")
        self.assertEqual(projection.leverage, "1:100")
        self.assertFalse(hasattr(projection, "model"))
        self.assertFalse(hasattr(projection, "modeling_mode"))

    def test_unsupported_configuration_is_unavailable(self) -> None:
        payload = SchemaReferencedPayload(
            SchemaRef(SchemaName("example-execution"), SchemaVersion(0, 1, 0)),
            {"opaque": True},
        )
        self.assertIsNone(Mt5ExperimentContextProjector().project(payload))

    def test_malformed_exact_configuration_fails_closed(self) -> None:
        document = copy.deepcopy(_execution_document())
        del document["symbol"]
        with self.assertRaises(ContractValidationError):
            Mt5ExperimentContextProjector().project(
                SchemaReferencedPayload(MT5_EXECUTION_REF, document)
            )

    def test_metaeditor_build_evidence_projects_historical_runtime_facts(self) -> None:
        document = json.loads(
            (FIXTURES / "metaeditor-build-evidence.json").read_text(encoding="utf-8")
        )
        projection = MetaEditorBuildRuntimeProjector().project(
            SchemaReferencedPayload(METAEDITOR_EVIDENCE_REF, document)
        )

        self.assertEqual(projection.role, "build")
        self.assertEqual(projection.provider_namespace, "metaeditor")
        self.assertEqual(projection.version, "5.0.0.6104")
        self.assertEqual(str(projection.executable_digest), document["executable_digest"])

    def test_non_metaeditor_build_evidence_remains_unavailable(self) -> None:
        payload = SchemaReferencedPayload(
            SchemaRef(SchemaName("example-build-evidence"), SchemaVersion(0, 1, 0)),
            {"opaque": True},
        )
        self.assertIsNone(MetaEditorBuildRuntimeProjector().project(payload))


if __name__ == "__main__":
    unittest.main()
