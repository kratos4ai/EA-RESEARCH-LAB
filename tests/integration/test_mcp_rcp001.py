from __future__ import annotations

import asyncio
import hashlib
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


ROOT = Path(__file__).resolve().parents[2]
RCP001 = ROOT / "data" / "rcp-001" / "lab.sqlite3"
EXPECTED_DIGEST = "f95b223be6351dd51272a921d4ec0841bc2b29d710b2ebb04ef0fcbd6926c495"
QUERY_TOOLS = (
    "list_research_runs",
    "get_research_run",
    "list_run_evidence_objects",
    "list_run_datasets",
    "get_dataset",
    "list_dataset_analyses",
    "get_analysis",
    "get_canonical_chain",
)


def _digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


class Rcp001McpReadTests(unittest.TestCase):
    def test_progressive_stdio_navigation_uses_only_persisted_read_model(self) -> None:
        canonical_before = _digest(RCP001)
        self.assertEqual(canonical_before, EXPECTED_DIGEST)
        with tempfile.TemporaryDirectory(prefix="earl-phase09-mcp-rcp001-") as name:
            database = Path(name) / "lab.sqlite3"
            shutil.copy2(RCP001, database)
            copy_before = _digest(database)
            observation = asyncio.run(self._navigate(database))
            self.assertEqual(_digest(database), copy_before)
        self.assertEqual(_digest(RCP001), canonical_before)

        self.assertEqual(observation["tools"], QUERY_TOOLS)
        self.assertEqual(observation["resources"], 0)
        self.assertEqual(observation["prompts"], 0)
        run = observation["run"]
        context = run["experiment_context"]
        self.assertEqual(
            context,
            {
                "instrument": "EURUSD",
                "timeframe": "H1",
                "start_date": "2026-01-01",
                "end_date": "2026-06-30",
                "requested_initial_capital": "1000",
                "currency": "USD",
                "leverage": "1:100",
            },
        )
        self.assertEqual(
            run["execution_reproducibility"]["level"], "best_effort"
        )
        self.assertEqual(len(run["execution_reproducibility"]["reasons"]), 3)
        runtimes = {item["role"]: item for item in run["provider_runtimes"]}
        self.assertEqual(runtimes["build"]["provider_namespace"], "metaeditor")
        self.assertEqual(runtimes["build"]["version"], "5.0.0.6104")
        self.assertNotIn("execution", runtimes)

        datasets = observation["datasets"]
        self.assertEqual(len(datasets), 3)
        self.assertEqual(len({item["summary"]["dataset_id"] for item in datasets}), 3)
        self.assertEqual(
            {item["summary"]["content_schema"] for item in datasets},
            {
                "urn:ea-research-lab:schema:execution-summary:0.1.0",
                "urn:ea-research-lab:schema:realized-execution-event-series:0.1.0",
                "urn:ea-research-lab:schema:account-balance-event-series:0.1.0",
            },
        )
        self.assertTrue(
            all(item["summary"]["content_digest"] for item in datasets)
        )
        self.assertTrue(
            all(item["summary"]["transformation_id"] for item in datasets)
        )
        self.assertTrue(
            all(item["summary"]["transformation_version"] for item in datasets)
        )
        execution = next(
            item["execution_summary"]
            for item in datasets
            if item["execution_summary"] is not None
        )
        self.assertEqual(
            execution,
            {
                "total_trades": 135,
                "winning_trades": 43,
                "losing_trades": 92,
                "net_profit": "2.63",
                "currency": "USD",
                "initial_deposit": "1000.00",
            },
        )
        self.assertTrue(all("payload" not in item for item in datasets))

        analysis = observation["analysis"]
        self.assertEqual(len(analysis["input_datasets"]), 3)
        self.assertTrue(analysis["summary"]["analysis_result_id"])
        self.assertTrue(analysis["summary"]["analysis_definition_id"])
        self.assertTrue(analysis["summary"]["analysis_version"])
        self.assertTrue(analysis["summary"]["result_digest"])
        result = analysis["bounded_result"]
        self.assertEqual(
            {
                "net_return": result["aggregate_metrics"]["net_return"]["value"],
                "win_rate": result["aggregate_metrics"]["win_rate"]["value"],
                "loss_rate": result["aggregate_metrics"]["loss_rate"]["value"],
                "profit_factor": result["aggregate_metrics"]["profit_factor"]["value"],
                "payoff_ratio": result["aggregate_metrics"]["payoff_ratio"]["value"],
                "drawdown_amount": result["event_balance_analysis"][
                    "event_balance_max_drawdown"
                ]["amount"]["value"],
                "drawdown_rate": result["event_balance_analysis"][
                    "event_balance_max_drawdown"
                ]["rate"]["value"],
            },
            {
                "net_return": "0.002630000000",
                "win_rate": "0.318518518519",
                "loss_rate": "0.681481481481",
                "profit_factor": "1.014333206169",
                "payoff_ratio": "2.170201278316",
                "drawdown_amount": "37.480000000000",
                "drawdown_rate": "0.036475820657",
            },
        )

        evidence = observation["evidence"]
        self.assertEqual(len(evidence), 3)
        self.assertTrue(all(item["byte_length"] > 0 for item in evidence))
        self.assertTrue(all(len(item["content_digest"]) == 64 for item in evidence))
        self.assertTrue(all(item["media_type"] for item in evidence))
        self.assertTrue(all(item["provider_namespace"] for item in evidence))
        self.assertTrue(all("content" not in item for item in evidence))
        self.assertTrue(all("path" not in item for item in evidence))

        chain = observation["chain"]
        self.assertEqual(chain["provenance"]["run_id"], run["summary"]["run_id"])
        self.assertEqual(len(chain["provenance"]["evidence_manifests"]), 1)
        self.assertEqual(len(chain["datasets"]), 3)
        self.assertEqual(
            chain["analysis"]["summary"]["analysis_result_id"],
            analysis["summary"]["analysis_result_id"],
        )

    async def _navigate(self, database: Path) -> dict[str, object]:
        environment = os.environ.copy()
        environment.update(
            {
                "EA_RESEARCH_LAB_METAEDITOR": "PROVIDER_EXECUTION_FORBIDDEN",
                "EA_RESEARCH_LAB_MT5_TERMINAL": "PROVIDER_EXECUTION_FORBIDDEN",
                "EA_RESEARCH_LAB_METAEDITOR_INTEGRATION": "0",
                "EA_RESEARCH_LAB_MT5_INTEGRATION": "0",
            }
        )
        parameters = StdioServerParameters(
            command=sys.executable,
            args=[
                "-m",
                "apps.mcp_adapter",
                "--mode",
                "read-only",
                "--database",
                str(database),
            ],
            env=environment,
            cwd=ROOT,
        )
        async with stdio_client(parameters) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                tools = await session.list_tools()
                tool_names = tuple(tool.name for tool in tools.tools)
                resources = await session.list_resources()
                prompts = await session.list_prompts()

                runs = (await session.call_tool(
                    "list_research_runs", {"page_size": 20}
                )).structured_content
                self.assertEqual(len(runs["items"]), 1)
                run_id = runs["items"][0]["run_id"]
                run = (await session.call_tool(
                    "get_research_run", {"run_id": run_id}
                )).structured_content
                manifest_id = run["summary"]["evidence_manifest"]["manifest_id"]

                dataset_page = (await session.call_tool(
                    "list_run_datasets", {"run_id": run_id, "page_size": 20}
                )).structured_content
                invalid_cursor = await session.call_tool(
                    "list_run_datasets",
                    {"run_id": run_id, "page_size": 20, "cursor": "invalid"},
                )
                self.assertTrue(invalid_cursor.is_error)
                datasets = []
                analysis_ids = set()
                for summary in dataset_page["items"]:
                    dataset_id = summary["dataset_id"]
                    datasets.append((await session.call_tool(
                        "get_dataset", {"dataset_id": dataset_id}
                    )).structured_content)
                    analyses = (await session.call_tool(
                        "list_dataset_analyses",
                        {"dataset_id": dataset_id, "page_size": 20},
                    )).structured_content
                    analysis_ids.update(
                        item["analysis_result_id"] for item in analyses["items"]
                    )
                self.assertEqual(len(analysis_ids), 1)
                analysis_id = analysis_ids.pop()
                analysis = (await session.call_tool(
                    "get_analysis", {"analysis_result_id": analysis_id}
                )).structured_content
                evidence = (await session.call_tool(
                    "list_run_evidence_objects",
                    {
                        "run_id": run_id,
                        "manifest_id": manifest_id,
                        "page_size": 20,
                    },
                )).structured_content
                chain = (await session.call_tool(
                    "get_canonical_chain",
                    {
                        "build_record_id": run["build_record_id"],
                        "run_id": run_id,
                        "analysis_result_id": analysis_id,
                    },
                )).structured_content
                return {
                    "tools": tool_names,
                    "resources": len(resources.resources),
                    "prompts": len(prompts.prompts),
                    "run": run,
                    "datasets": datasets,
                    "analysis": analysis,
                    "evidence": evidence["items"],
                    "chain": chain,
                }


if __name__ == "__main__":
    unittest.main()
