"""Parser for the empirically observed MT5 Strategy Tester HTML report."""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from html.parser import HTMLParser

from ea_research_lab.application.dataset import TransformationRequest
from ea_research_lab.contracts import validate_document
from ea_research_lab.domain.provenance import SchemaReferencedPayload
from ea_research_lab.domain.values import SchemaName, SchemaRef, SchemaVersion


_REPORT_NAMESPACE = "metatrader5.strategy-tester.report"
_CONTENT_REF = SchemaRef(SchemaName("execution-summary"), SchemaVersion(0, 1, 0))
_LABELS = {
    "Currency:": "currency",
    "Initial Deposit:": "initial_deposit",
    "Total Net Profit:": "net_profit",
    "Gross Profit:": "gross_profit",
    "Gross Loss:": "gross_loss",
    "Total Trades:": "total_trades",
    "Profit Trades (% of total):": "winning_trades",
    "Loss Trades (% of total):": "losing_trades",
}
_MONEY = re.compile(
    r"-?(?:0|[1-9][0-9]*|[1-9][0-9]{0,2}(?: [0-9]{3})+)\.[0-9]{2}"
)
_COUNT_WITH_PERCENT = re.compile(r"([0-9]+) \([0-9]+\.[0-9]{2}%\)")


class Mt5ReportError(ValueError):
    """Safe failure for an unsupported or invalid observed report."""


class _CellParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.cells: list[str] = []
        self._parts: list[str] | None = None

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        if tag in {"td", "th"}:
            if self._parts is not None:
                raise Mt5ReportError("MT5 report cell layout is unsupported.")
            self._parts = []

    def handle_data(self, data: str) -> None:
        if self._parts is not None:
            self._parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"td", "th"} and self._parts is not None:
            self.cells.append(_clean("".join(self._parts)))
            self._parts = None

    def close(self) -> None:
        super().close()
        if self._parts is not None:
            raise Mt5ReportError("MT5 report cell layout is unsupported.")


class Mt5ReportTransformer:
    """Transform exactly one captured report into a neutral execution summary."""

    def transform(self, request: TransformationRequest) -> SchemaReferencedPayload:
        reports = tuple(
            item
            for item in request.raw_evidence
            if item.evidence_object.provider_namespace == _REPORT_NAMESPACE
            and item.evidence_object.media_type == "text/html"
        )
        if len(reports) != 1:
            raise Mt5ReportError(
                "Transformation requires exactly one supported MT5 report."
            )
        document = _parse_report(reports[0].content)
        validate_document(document)
        return SchemaReferencedPayload(_CONTENT_REF, document)


def _parse_report(content: bytes) -> dict[str, object]:
    if not isinstance(content, bytes) or not content.startswith(b"\xff\xfe"):
        raise Mt5ReportError("MT5 report encoding is unsupported.")
    try:
        text = content[2:].decode("utf-16le")
    except UnicodeError as error:
        raise Mt5ReportError("MT5 report encoding is unsupported.") from error
    parser = _CellParser()
    try:
        parser.feed(text)
        parser.close()
    except (UnicodeError, ValueError) as error:
        raise Mt5ReportError("MT5 report layout is unsupported.") from error

    extracted: dict[str, str] = {}
    for index, cell in enumerate(parser.cells):
        field = _LABELS.get(cell)
        if field is None:
            continue
        if field in extracted or index + 1 >= len(parser.cells):
            raise Mt5ReportError("MT5 report contains duplicate or incomplete fields.")
        value = parser.cells[index + 1]
        if not value:
            raise Mt5ReportError("MT5 report contains an empty required field.")
        extracted[field] = value
    if set(extracted) != set(_LABELS.values()):
        raise Mt5ReportError("MT5 report is missing a required field.")

    total = _parse_count(extracted["total_trades"])
    winning = _parse_count_with_percent(extracted["winning_trades"])
    losing = _parse_count_with_percent(extracted["losing_trades"])
    if winning + losing != total:
        raise Mt5ReportError("MT5 report trade counts are contradictory.")

    document: dict[str, object] = {
        "schema_name": str(_CONTENT_REF.name),
        "schema_version": str(_CONTENT_REF.version),
        "currency": _parse_currency(extracted["currency"]),
        "initial_deposit": _parse_money(extracted["initial_deposit"]),
        "net_profit": _parse_money(extracted["net_profit"]),
        "gross_profit": _parse_money(extracted["gross_profit"]),
        "gross_loss": _parse_money(extracted["gross_loss"]),
        "total_trades": total,
        "winning_trades": winning,
        "losing_trades": losing,
    }
    return document


def _clean(value: str) -> str:
    return " ".join(value.replace("\xa0", " ").split())


def _parse_currency(value: str) -> str:
    if re.fullmatch(r"[A-Z]{3}", value) is None:
        raise Mt5ReportError("MT5 report currency is unsupported.")
    return value


def _parse_money(value: str) -> str:
    if _MONEY.fullmatch(value) is None:
        raise Mt5ReportError("MT5 report monetary value is unsupported.")
    try:
        amount = Decimal(value.replace(" ", ""))
    except InvalidOperation as error:
        raise Mt5ReportError("MT5 report monetary value is invalid.") from error
    if amount == 0:
        amount = abs(amount)
    return f"{amount:.2f}"


def _parse_count(value: str) -> int:
    if re.fullmatch(r"[0-9]+", value) is None:
        raise Mt5ReportError("MT5 report trade count is invalid.")
    return int(value)


def _parse_count_with_percent(value: str) -> int:
    match = _COUNT_WITH_PERCENT.fullmatch(value)
    if match is None:
        raise Mt5ReportError("MT5 report trade count is invalid.")
    return int(match.group(1))
