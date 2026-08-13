from __future__ import annotations

import hashlib
import logging
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from apps.visual_analytics.view_model import (
    UNAVAILABLE,
    build_analysis_view,
    build_dataset_view,
    build_research_overview,
    dataset_label,
    execution_environment_fields,
)
from ea_research_lab.application.context import RequestContext
from ea_research_lab.application.identity import new_entity_id
from ea_research_lab.application.research_query import PageRequest
from ea_research_lab.domain.identifiers import RequestId
from ea_research_lab.infrastructure.composition import compose_read_only_platform
from ea_research_lab.infrastructure.metaeditor import MetaEditorBuildProvider
from ea_research_lab.infrastructure.mt5_strategy_tester import (
    Mt5StrategyTesterProvider,
)


ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "apps" / "visual_analytics" / "app.py"
RCP001 = ROOT / "data" / "rcp-001" / "lab.sqlite3"


def _digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


class Rcp001VisualAnalyticsTests(unittest.TestCase):
    def test_disposable_checkpoint_renders_complete_read_only_research_flow(self) -> None:
        canonical_before = _digest(RCP001)
        with tempfile.TemporaryDirectory(prefix="earl-phase08-rcp001-") as name:
            database = Path(name) / "lab.sqlite3"
            shutil.copy2(RCP001, database)
            copy_before = _digest(database)
            context = RequestContext(new_entity_id(RequestId), "phase08-validation")
            with compose_read_only_platform(
                database, logging.getLogger("ea_research_lab.phase08.validation")
            ) as api:
                runs = api.list_research_runs(context, PageRequest(20))
                self.assertEqual(len(runs.items), 1)
                self.assertIsNone(runs.next_cursor)
                run = api.get_research_run(context, runs.items[0].run_id)
                dataset_page = api.list_run_datasets(
                    context, run.summary.run_id, PageRequest(20)
                )
                datasets = tuple(
                    api.get_dataset(context, item.dataset_id)
                    for item in dataset_page.items
                )
                analysis_ids = {
                    item.analysis_result_id
                    for dataset in datasets
                    for item in api.list_dataset_analyses(
                        context, dataset.summary.dataset_id, PageRequest(20)
                    ).items
                }
                self.assertEqual(len(analysis_ids), 1)
                analysis = api.get_analysis(context, analysis_ids.pop())
                evidence = api.list_run_evidence_objects(
                    context,
                    run.summary.run_id,
                    run.summary.evidence_manifest.manifest_id,
                    PageRequest(20),
                )
                chain = api.get_canonical_chain(
                    context,
                    run.build_record_id,
                    run.summary.run_id,
                    analysis.summary.analysis_result_id,
                )

            summaries = {str(item.summary.content_schema): item for item in datasets}
            execution = summaries[
                "urn:ea-research-lab:schema:execution-summary:0.1.0"
            ].execution_summary
            overview = build_research_overview(run, execution, analysis)
            analysis_view = build_analysis_view(
                analysis,
                {
                    str(item.summary.dataset_id): dataset_label(
                        item.summary.content_schema
                    )
                    for item in datasets
                },
            )
            result = analysis.bounded_result.value

            self.assertEqual(
                tuple(value for _, value in overview.experiment_context),
                (
                    "EURUSD",
                    "H1",
                    "2026-01-01",
                    "2026-06-30",
                    "USD 1,000.00",
                    "USD",
                    "1:100",
                ),
            )
            self.assertEqual(
                (
                    execution.total_trades,
                    execution.winning_trades,
                    execution.losing_trades,
                    str(execution.net_profit),
                ),
                (135, 43, 92, "2.63"),
            )
            self.assertEqual(
                tuple((item.label, item.value) for item in overview.winning_losing),
                (("Winning", 43), ("Losing", 92)),
            )
            self.assertEqual(
                tuple(str(item.value) for item in overview.realized_pnl_summary),
                (
                    "-6.720000000000",
                    "-1.030000000000",
                    "0.044370370370",
                    "22.900000000000",
                ),
            )
            self.assertEqual(
                {
                    "net_return": result["aggregate_metrics"]["net_return"]["value"],
                    "win_rate": result["aggregate_metrics"]["win_rate"]["value"],
                    "loss_rate": result["aggregate_metrics"]["loss_rate"]["value"],
                    "expected_payoff": result["aggregate_metrics"]["expected_payoff"]["value"],
                    "profit_factor": result["aggregate_metrics"]["profit_factor"]["value"],
                    "average_winner": result["aggregate_metrics"]["average_winning_result"]["value"],
                    "average_loser": result["aggregate_metrics"]["average_losing_magnitude"]["value"],
                    "payoff_ratio": result["aggregate_metrics"]["payoff_ratio"]["value"],
                    "positive_streak": result["realized_execution_sequence"]["longest_positive_streak"],
                    "negative_streak": result["realized_execution_sequence"]["longest_negative_streak"],
                    "drawdown_amount": result["event_balance_analysis"]["event_balance_max_drawdown"]["amount"]["value"],
                    "drawdown_rate": result["event_balance_analysis"]["event_balance_max_drawdown"]["rate"]["value"],
                },
                {
                    "net_return": "0.002630000000",
                    "win_rate": "0.318518518519",
                    "loss_rate": "0.681481481481",
                    "expected_payoff": "0.019481481481",
                    "profit_factor": "1.014333206169",
                    "average_winner": "4.328372093023",
                    "average_loser": "1.994456521739",
                    "payoff_ratio": "2.170201278316",
                    "positive_streak": 3,
                    "negative_streak": 7,
                    "drawdown_amount": "37.480000000000",
                    "drawdown_rate": "0.036475820657",
                },
            )
            self.assertEqual(
                {dataset_label(item.summary.content_schema) for item in datasets},
                {
                    "Execution Summary",
                    "Realized Execution Events",
                    "Account Balance Events",
                },
            )
            self.assertEqual(len({item.summary.dataset_id for item in datasets}), 3)
            self.assertEqual(len({item.summary.content_digest for item in datasets}), 3)
            self.assertTrue(all(item.summary.transformation_id for item in datasets))
            self.assertEqual(len(analysis_view.inputs), 3)
            self.assertTrue(analysis_view.bounded_metrics)
            self.assertEqual(len(evidence.items), 3)
            self.assertTrue(all(not hasattr(item, "content") for item in evidence.items))
            self.assertEqual(len(chain.datasets), 3)
            self.assertEqual(chain.provenance.run_id, run.summary.run_id)
            self.assertEqual(run.execution_reproducibility.level.value, "best_effort")
            self.assertEqual(len(run.execution_reproducibility.reasons), 3)
            environment = dict(execution_environment_fields(run))
            self.assertEqual(environment["Build Provider"], "metaeditor")
            self.assertEqual(environment["Build Provider Version"], "5.0.0.6104")
            self.assertNotEqual(environment["Build Executable Digest"], UNAVAILABLE)
            self.assertEqual(environment["Execution Runtime Version"], UNAVAILABLE)

            with (
                patch.dict(
                    os.environ, {"EA_RESEARCH_LAB_DATABASE": str(database)}
                ),
                patch.object(
                    MetaEditorBuildProvider,
                    "build",
                    side_effect=AssertionError("MetaEditor must not run."),
                ) as build,
                patch.object(
                    Mt5StrategyTesterProvider,
                    "execute",
                    side_effect=AssertionError("MT5 must not run."),
                ) as execute,
            ):
                app = AppTest.from_file(str(APP)).run(timeout=30)

            self.assertEqual(list(app.exception), [])
            self.assertEqual(list(app.error), [])
            self.assertEqual(len(app.selectbox[0].options), 1)
            self.assertEqual(len(app.selectbox[1].options), 3)
            self.assertEqual(len(app.selectbox[2].options), 1)
            self.assertEqual(len(app.get("vega_lite_chart")), 2)
            self.assertIn(
                "Canonical provenance verified",
                tuple(item.value for item in app.success),
            )
            metrics = {(item.label, item.value) for item in app.metric}
            self.assertTrue(
                {
                    ("Net Profit", "USD 2.63"),
                    ("Net Return", "0.263%"),
                    ("Win Rate", "31.852%"),
                    ("Loss Rate", "68.148%"),
                    ("Event-Balance Max Drawdown", "USD 37.48"),
                    ("Execution Runtime Version", UNAVAILABLE),
                }.issubset(metrics)
            )
            rendered = " ".join(
                item.value
                for family in (app.text, app.caption, app.markdown, app.code)
                for item in family
            )
            for forbidden in (
                "MA_CROSS",
                "POSITION_OPEN",
                "POSITION_CLOSE",
                "POSITION_REVERSE",
                "TRADE_ERROR",
                "equity drawdown",
            ):
                self.assertNotIn(forbidden, rendered)
            build.assert_not_called()
            execute.assert_not_called()
            self.assertEqual(_digest(database), copy_before)

        self.assertEqual(_digest(RCP001), canonical_before)


if __name__ == "__main__":
    unittest.main()
