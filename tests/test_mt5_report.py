from __future__ import annotations

import hashlib
import unittest
from collections.abc import Mapping
from pathlib import Path

from ea_research_lab.application.context import RequestContext
from ea_research_lab.application.dataset import TransformationRequest, transform_dataset
from ea_research_lab.application.execution import CollectedRawEvidence
from ea_research_lab.application.identity import new_entity_id
from ea_research_lab.contracts import validate_document
from ea_research_lab.domain.evidence import (
    EvidenceCollectionOutcome,
    RawEvidenceManifest,
    RawEvidenceManifestRef,
    RawEvidenceObject,
)
from ea_research_lab.domain.identifiers import (
    RawEvidenceManifestId,
    RawEvidenceObjectId,
    RequestId,
    RunId,
    TransformationId,
)
from ea_research_lab.domain.provenance import EvidenceProvenance
from ea_research_lab.domain.values import (
    DefinitionVersion,
    Sha256Digest,
    UtcTimestamp,
)
from ea_research_lab.infrastructure.mt5_report import Mt5ReportTransformer
from ea_research_lab.infrastructure.mt5_report import (
    Mt5AccountBalanceEventSeriesTransformer,
    Mt5RealizedExecutionEventSeriesTransformer,
)


FIXTURE = Path(__file__).parent / "fixtures" / "mt5" / "strategy-tester-report.html"
KNOWN_ACTIVITY_FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "mt5"
    / "strategy-tester-report-known-activity.html"
)


def _plain(value: object) -> object:
    if isinstance(value, Mapping):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_plain(item) for item in value]
    return value


def _report_bytes(text: str | None = None) -> bytes:
    source = FIXTURE.read_text(encoding="utf-8") if text is None else text
    return b"\xff\xfe" + source.encode("utf-16le")


def _collected(
    content: bytes,
    media_type: str = "text/html",
    namespace: str = "metatrader5.strategy-tester.report",
) -> CollectedRawEvidence:
    return CollectedRawEvidence(
        RawEvidenceObject(
            new_entity_id(RawEvidenceObjectId),
            media_type,
            len(content),
            Sha256Digest(hashlib.sha256(content).hexdigest()),
            provider_namespace=namespace,
        ),
        content,
    )


def _request(content: bytes, *, include_log: bool = False) -> TransformationRequest:
    collected = [_collected(content)]
    if include_log:
        collected.append(
            _collected(
                b"\xff\xfelog bytes",
                "text/plain",
                "metatrader5.strategy-tester.terminal-log",
            )
        )
    return _request_from_evidence(tuple(collected))


def _request_from_evidence(
    collected: tuple[CollectedRawEvidence, ...],
) -> TransformationRequest:
    manifest = RawEvidenceManifest(
        new_entity_id(RawEvidenceManifestId),
        new_entity_id(RunId),
        tuple(item.evidence_object for item in collected),
        UtcTimestamp.parse("2026-08-11T12:00:00Z"),
        EvidenceCollectionOutcome.COMPLETED,
    )
    reference = RawEvidenceManifestRef(
        manifest.manifest_id,
        manifest.run_id,
        Sha256Digest("a" * 64),
    )
    return TransformationRequest(
        RequestContext(new_entity_id(RequestId), "mt5-report-test"),
        EvidenceProvenance(manifest, reference),
        collected,
        new_entity_id(TransformationId),
        DefinitionVersion("mt5-execution-summary-1"),
    )


def _known_report_bytes(text: str | None = None) -> bytes:
    source = (
        KNOWN_ACTIVITY_FIXTURE.read_text(encoding="utf-8")
        if text is None
        else text
    )
    return b"\xff\xfe" + source.encode("utf-16le")


def _assert_no_float(test: unittest.TestCase, value: object) -> None:
    test.assertNotIsInstance(value, float)
    if isinstance(value, Mapping):
        for item in value.values():
            _assert_no_float(test, item)
    elif isinstance(value, tuple):
        for item in value:
            _assert_no_float(test, item)


class Mt5ReportTransformerTests(unittest.TestCase):
    def test_controlled_report_produces_exact_neutral_summary(self) -> None:
        content = _report_bytes()
        request = _request(content, include_log=True)

        outcome = transform_dataset(Mt5ReportTransformer(), request)

        self.assertIsNone(outcome.failure)
        self.assertEqual(
            _plain(outcome.dataset.content.payload.value),
            {
                "schema_name": "execution-summary",
                "schema_version": "0.1.0",
                "currency": "USD",
                "initial_deposit": "10000.00",
                "net_profit": "0.00",
                "gross_profit": "0.00",
                "gross_loss": "0.00",
                "total_trades": 0,
                "winning_trades": 0,
                "losing_trades": 0,
            },
        )
        _assert_no_float(self, outcome.dataset.content.payload.value)
        validate_document(_plain(outcome.dataset.content.payload.value))
        validate_document(_plain(outcome.dataset.manifest.value))
        self.assertEqual(
            outcome.dataset.manifest.value["content_digest"],
            str(outcome.dataset.content.content_digest),
        )

    def test_repeated_transform_is_byte_and_digest_deterministic(self) -> None:
        request = _request(_report_bytes())

        first = transform_dataset(Mt5ReportTransformer(), request).dataset
        second = transform_dataset(Mt5ReportTransformer(), request).dataset

        self.assertEqual(first.content.canonical_bytes, second.content.canonical_bytes)
        self.assertEqual(first.content.content_digest, second.content.content_digest)

    def test_decimal_normalization_handles_observed_grouping_negative_and_zero(self) -> None:
        text = FIXTURE.read_text(encoding="utf-8").replace(
            "<td>Total Net Profit:</td><td>0.00</td>",
            "<td>Total Net Profit:</td><td>-1 234.50</td>",
        )

        dataset = transform_dataset(
            Mt5ReportTransformer(), _request(_report_bytes(text))
        ).dataset
        values = dataset.content.payload.value

        self.assertEqual(values["initial_deposit"], "10000.00")
        self.assertEqual(values["net_profit"], "-1234.50")
        self.assertEqual(values["gross_profit"], "0.00")

    def test_report_evidence_is_not_modified(self) -> None:
        content = _report_bytes()
        request = _request(content)
        before = request.raw_evidence[0].content

        transform_dataset(Mt5ReportTransformer(), request)

        self.assertEqual(request.raw_evidence[0].content, before)
        self.assertEqual(hashlib.sha256(before).digest(), hashlib.sha256(content).digest())

    def test_encoding_localization_and_layout_fail_closed(self) -> None:
        source = FIXTURE.read_text(encoding="utf-8")
        cases = (
            source.encode("utf-8"),
            _report_bytes(source.replace("Currency:", "Moeda:")),
            _report_bytes(source.replace("<td>", "<div>").replace("</td>", "</div>")),
        )
        for content in cases:
            with self.subTest(prefix=content[:8]):
                outcome = transform_dataset(Mt5ReportTransformer(), _request(content))
                self.assertIsNone(outcome.dataset)
                self.assertEqual(
                    outcome.failure.code.value,
                    "dataset_transformation_failed",
                )

    def test_missing_and_duplicate_required_fields_fail_closed(self) -> None:
        source = FIXTURE.read_text(encoding="utf-8")
        row = "<tr><td>Gross Profit:</td><td>0.00</td></tr>"
        cases = (
            source.replace(row, ""),
            source.replace("</table>", f"{row}\n</table>"),
        )
        for text in cases:
            with self.subTest(duplicate=text.count("Gross Profit:") > 1):
                outcome = transform_dataset(
                    Mt5ReportTransformer(), _request(_report_bytes(text))
                )
                self.assertIsNone(outcome.dataset)
                self.assertIsNotNone(outcome.failure)

    def test_malformed_money_and_counts_fail_closed(self) -> None:
        source = FIXTURE.read_text(encoding="utf-8")
        cases = (
            source.replace("10 000.00", "10,000.00"),
            source.replace(
                "<td>Total Trades:</td><td>0</td>",
                "<td>Total Trades:</td><td>0.0</td>",
            ),
            source.replace("0 (0.00%)", "invalid", 1),
        )
        for text in cases:
            with self.subTest():
                outcome = transform_dataset(
                    Mt5ReportTransformer(), _request(_report_bytes(text))
                )
                self.assertIsNone(outcome.dataset)
                self.assertIsNotNone(outcome.failure)

    def test_contradictory_trade_counts_fail_closed(self) -> None:
        source = FIXTURE.read_text(encoding="utf-8").replace(
            "<td>Profit Trades (% of total):</td><td>0 (0.00%)</td>",
            "<td>Profit Trades (% of total):</td><td>1 (100.00%)</td>",
        )

        outcome = transform_dataset(
            Mt5ReportTransformer(), _request(_report_bytes(source))
        )

        self.assertIsNone(outcome.dataset)
        self.assertIsNotNone(outcome.failure)


class Mt5DetailedDatasetTransformerTests(unittest.TestCase):
    def test_known_activity_produces_both_exact_dataset_products(self) -> None:
        request = _request(_known_report_bytes(), include_log=True)

        realized = transform_dataset(
            Mt5RealizedExecutionEventSeriesTransformer(), request
        ).dataset
        balances = transform_dataset(
            Mt5AccountBalanceEventSeriesTransformer(), request
        ).dataset

        self.assertEqual(
            _plain(realized.content.payload.value),
            {
                "schema_name": "realized-execution-event-series",
                "schema_version": "0.1.0",
                "currency": "USD",
                "time_basis": "source_local_time_without_offset",
                "events": [
                    {
                        "sequence": 0,
                        "source_record_id": "3",
                        "local_time": "2026-08-03T00:00:20",
                        "instrument": "EURUSD",
                        "side": "sell",
                        "volume": "0.01",
                        "price": "1.15437",
                        "realized_pnl": "-0.04",
                        "commission": "0.00",
                        "swap": "0.00",
                    },
                    {
                        "sequence": 1,
                        "source_record_id": "5",
                        "local_time": "2026-08-03T00:00:40",
                        "instrument": "EURUSD",
                        "side": "buy",
                        "volume": "0.01",
                        "price": "1.15395",
                        "realized_pnl": "0.42",
                        "commission": "0.00",
                        "swap": "0.00",
                    },
                ],
            },
        )
        self.assertEqual(
            _plain(balances.content.payload.value),
            {
                "schema_name": "account-balance-event-series",
                "schema_version": "0.1.0",
                "currency": "USD",
                "time_basis": "source_local_time_without_offset",
                "observations": [
                    {
                        "sequence": 0,
                        "source_record_id": "1",
                        "local_time": "2026-08-03T00:00:00",
                        "balance": "10000.00",
                    },
                    {
                        "sequence": 1,
                        "source_record_id": "2",
                        "local_time": "2026-08-03T00:00:00",
                        "balance": "10000.00",
                    },
                    {
                        "sequence": 2,
                        "source_record_id": "3",
                        "local_time": "2026-08-03T00:00:20",
                        "balance": "9999.96",
                    },
                    {
                        "sequence": 3,
                        "source_record_id": "4",
                        "local_time": "2026-08-03T00:00:20",
                        "balance": "9999.96",
                    },
                    {
                        "sequence": 4,
                        "source_record_id": "5",
                        "local_time": "2026-08-03T00:00:40",
                        "balance": "10000.38",
                    },
                ],
            },
        )
        for dataset in (realized, balances):
            _assert_no_float(self, dataset.content.payload.value)
            validate_document(_plain(dataset.content.payload.value))
            validate_document(_plain(dataset.manifest.value))
            self.assertEqual(
                dataset.manifest.value["content_digest"],
                str(dataset.content.content_digest),
            )
            self.assertEqual(
                dataset.provenance.input_manifests,
                (request.evidence.manifest_ref,),
            )

    def test_both_products_are_content_deterministic_not_entity_deterministic(self) -> None:
        request = _request(_known_report_bytes())
        for transformer in (
            Mt5RealizedExecutionEventSeriesTransformer(),
            Mt5AccountBalanceEventSeriesTransformer(),
        ):
            with self.subTest(transformer=type(transformer).__name__):
                first = transform_dataset(transformer, request).dataset
                second = transform_dataset(transformer, request).dataset
                self.assertNotEqual(
                    first.provenance.dataset_id, second.provenance.dataset_id
                )
                self.assertEqual(
                    first.content.canonical_bytes, second.content.canonical_bytes
                )
                self.assertEqual(
                    first.content.content_digest, second.content.content_digest
                )

    def test_source_identifiers_are_preserved_as_opaque_strings(self) -> None:
        text = KNOWN_ACTIVITY_FIXTURE.read_text(encoding="utf-8").replace(
            "<td>3</td><td>EURUSD</td><td>sell</td><td>out</td>",
            "<td>0003</td><td>EURUSD</td><td>sell</td><td>out</td>",
        )

        dataset = transform_dataset(
            Mt5RealizedExecutionEventSeriesTransformer(),
            _request(_known_report_bytes(text)),
        ).dataset

        self.assertEqual(
            dataset.content.payload.value["events"][0]["source_record_id"],
            "0003",
        )

    def test_report_bytes_remain_immutable_for_both_products(self) -> None:
        content = _known_report_bytes()
        request = _request(content)
        before = request.raw_evidence[0].content

        transform_dataset(Mt5RealizedExecutionEventSeriesTransformer(), request)
        transform_dataset(Mt5AccountBalanceEventSeriesTransformer(), request)

        self.assertEqual(request.raw_evidence[0].content, before)
        self.assertEqual(hashlib.sha256(before).hexdigest(), hashlib.sha256(content).hexdigest())

    def test_missing_and_duplicate_report_evidence_fail_closed(self) -> None:
        content = _known_report_bytes()
        requests = (
            _request_from_evidence(
                (
                    _collected(
                        b"\xff\xfelog",
                        "text/plain",
                        "metatrader5.strategy-tester.terminal-log",
                    ),
                )
            ),
            _request_from_evidence((_collected(content), _collected(content))),
        )
        for request in requests:
            for transformer in (
                Mt5RealizedExecutionEventSeriesTransformer(),
                Mt5AccountBalanceEventSeriesTransformer(),
            ):
                with self.subTest(
                    evidence=len(request.raw_evidence),
                    transformer=type(transformer).__name__,
                ):
                    outcome = transform_dataset(transformer, request)
                    self.assertIsNone(outcome.dataset)
                    self.assertIsNotNone(outcome.failure)

    def test_unsupported_or_malformed_deals_fail_closed(self) -> None:
        source = KNOWN_ACTIVITY_FIXTURE.read_text(encoding="utf-8")
        cases = (
            source.encode("utf-8"),
            _known_report_bytes(source.replace("<th>Deals</th>", "<th>Transações</th>")),
            _known_report_bytes(source.replace("<th>Deal</th>", "<th>Position</th>")),
            _known_report_bytes(source.replace(
                "<td>-0.04</td><td>9 999.96</td>",
                "<td>invalid</td><td>9 999.96</td>",
            )),
            _known_report_bytes(source.replace(
                "2026.08.03 00:00:20</td><td>3</td>",
                "2026.02.30 00:00:20</td><td>3</td>",
            )),
            _known_report_bytes(source.replace(
                "<td>4</td><td>EURUSD</td><td>sell</td><td>in</td>",
                "<td>3</td><td>EURUSD</td><td>sell</td><td>in</td>",
            )),
            _known_report_bytes(source.replace(
                "<td>10 000.38</td><td></td></tr>\n</table>",
                "<td>9 999.99</td><td></td></tr>\n</table>",
            )),
        )
        for content in cases:
            for transformer in (
                Mt5RealizedExecutionEventSeriesTransformer(),
                Mt5AccountBalanceEventSeriesTransformer(),
            ):
                with self.subTest(
                    prefix=content[:8], transformer=type(transformer).__name__
                ):
                    outcome = transform_dataset(transformer, _request(content))
                    self.assertIsNone(outcome.dataset)
                    self.assertIsNotNone(outcome.failure)


if __name__ == "__main__":
    unittest.main()
