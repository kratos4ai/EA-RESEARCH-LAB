"""Parser for the empirically observed MT5 Strategy Tester HTML report."""

from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from html.parser import HTMLParser

from ea_research_lab.application.dataset import TransformationRequest
from ea_research_lab.contracts import validate_document
from ea_research_lab.domain.provenance import SchemaReferencedPayload
from ea_research_lab.domain.values import SchemaName, SchemaRef, SchemaVersion


_REPORT_NAMESPACE = "metatrader5.strategy-tester.report"
_SUMMARY_REF = SchemaRef(SchemaName("execution-summary"), SchemaVersion(0, 1, 0))
_REALIZED_EVENTS_REF = SchemaRef(
    SchemaName("realized-execution-event-series"), SchemaVersion(0, 1, 0)
)
_BALANCE_EVENTS_REF = SchemaRef(
    SchemaName("account-balance-event-series"), SchemaVersion(0, 1, 0)
)
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
_UNSIGNED_DECIMAL = re.compile(r"(?:0|[1-9][0-9]*)\.[0-9]+")
_LOCAL_TIME = "%Y.%m.%d %H:%M:%S"
_DEALS_HEADER = (
    "Time",
    "Deal",
    "Symbol",
    "Type",
    "Direction",
    "Volume",
    "Price",
    "Order",
    "Commission",
    "Swap",
    "Profit",
    "Balance",
    "Comment",
)


class Mt5ReportError(ValueError):
    """Safe failure for an unsupported or invalid observed report."""


class _RowParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[tuple[str, ...]] = []
        self._row: list[str] | None = None
        self._parts: list[str] | None = None

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        if tag == "tr":
            if self._row is not None:
                raise Mt5ReportError("MT5 report row layout is unsupported.")
            self._row = []
        elif tag in {"td", "th"}:
            if self._row is None or self._parts is not None:
                raise Mt5ReportError("MT5 report cell layout is unsupported.")
            self._parts = []

    def handle_data(self, data: str) -> None:
        if self._parts is not None:
            self._parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"td", "th"} and self._parts is not None:
            if self._row is None:
                raise Mt5ReportError("MT5 report cell layout is unsupported.")
            self._row.append(_clean("".join(self._parts)))
            self._parts = None
        elif tag == "tr":
            if self._row is None or self._parts is not None:
                raise Mt5ReportError("MT5 report row layout is unsupported.")
            if any(self._row):
                self.rows.append(tuple(self._row))
            self._row = None

    def close(self) -> None:
        super().close()
        if self._parts is not None or self._row is not None:
            raise Mt5ReportError("MT5 report cell layout is unsupported.")


class Mt5ReportTransformer:
    """Transform exactly one captured report into a neutral execution summary."""

    def transform(self, request: TransformationRequest) -> SchemaReferencedPayload:
        document = _parse_summary(_parse_rows(_report_content(request)))
        validate_document(document)
        return SchemaReferencedPayload(_SUMMARY_REF, document)


class Mt5RealizedExecutionEventSeriesTransformer:
    """Transform one captured report into neutral realized execution events."""

    def transform(self, request: TransformationRequest) -> SchemaReferencedPayload:
        rows = _parse_rows(_report_content(request))
        currency = _parse_currency(_required_summary_value(rows, "Currency:"))
        events, _ = _parse_deals(rows)
        realized = tuple(event for event in events if event["direction"] == "out")
        if not realized:
            raise Mt5ReportError("MT5 report contains no realized execution event.")
        document = {
            "schema_name": str(_REALIZED_EVENTS_REF.name),
            "schema_version": str(_REALIZED_EVENTS_REF.version),
            "currency": currency,
            "time_basis": "source_local_time_without_offset",
            "events": [
                {
                    "sequence": sequence,
                    "source_record_id": event["source_record_id"],
                    "local_time": event["local_time"],
                    "instrument": event["instrument"],
                    "side": event["side"],
                    "volume": event["volume"],
                    "price": event["price"],
                    "realized_pnl": event["profit"],
                    "commission": event["commission"],
                    "swap": event["swap"],
                }
                for sequence, event in enumerate(realized)
            ],
        }
        validate_document(document)
        return SchemaReferencedPayload(_REALIZED_EVENTS_REF, document)


class Mt5AccountBalanceEventSeriesTransformer:
    """Transform one captured report into neutral event-indexed balances."""

    def transform(self, request: TransformationRequest) -> SchemaReferencedPayload:
        rows = _parse_rows(_report_content(request))
        currency = _parse_currency(_required_summary_value(rows, "Currency:"))
        events, _ = _parse_deals(rows)
        document = {
            "schema_name": str(_BALANCE_EVENTS_REF.name),
            "schema_version": str(_BALANCE_EVENTS_REF.version),
            "currency": currency,
            "time_basis": "source_local_time_without_offset",
            "observations": [
                {
                    "sequence": sequence,
                    "source_record_id": event["source_record_id"],
                    "local_time": event["local_time"],
                    "balance": event["balance"],
                }
                for sequence, event in enumerate(events)
            ],
        }
        validate_document(document)
        return SchemaReferencedPayload(_BALANCE_EVENTS_REF, document)


def _report_content(request: TransformationRequest) -> bytes:
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
    return reports[0].content


def _parse_rows(content: bytes) -> tuple[tuple[str, ...], ...]:
    if not isinstance(content, bytes) or not content.startswith(b"\xff\xfe"):
        raise Mt5ReportError("MT5 report encoding is unsupported.")
    try:
        text = content[2:].decode("utf-16le")
    except UnicodeError as error:
        raise Mt5ReportError("MT5 report encoding is unsupported.") from error
    parser = _RowParser()
    try:
        parser.feed(text)
        parser.close()
    except (UnicodeError, ValueError) as error:
        raise Mt5ReportError("MT5 report layout is unsupported.") from error

    return tuple(parser.rows)


def _parse_summary(rows: tuple[tuple[str, ...], ...]) -> dict[str, object]:
    cells = tuple(cell for row in rows for cell in row)
    extracted: dict[str, str] = {}
    for index, cell in enumerate(cells):
        field = _LABELS.get(cell)
        if field is None:
            continue
        if field in extracted or index + 1 >= len(cells):
            raise Mt5ReportError("MT5 report contains duplicate or incomplete fields.")
        value = cells[index + 1]
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
        "schema_name": str(_SUMMARY_REF.name),
        "schema_version": str(_SUMMARY_REF.version),
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


def _required_summary_value(
    rows: tuple[tuple[str, ...], ...], label: str
) -> str:
    values = tuple(
        row[index + 1]
        for row in rows
        for index, cell in enumerate(row[:-1])
        if cell == label
    )
    if len(values) != 1 or not values[0]:
        raise Mt5ReportError("MT5 report summary field is missing or ambiguous.")
    return values[0]


def _parse_deals(
    rows: tuple[tuple[str, ...], ...],
) -> tuple[tuple[dict[str, str], ...], str]:
    sections = tuple(index for index, row in enumerate(rows) if row == ("Deals",))
    if len(sections) != 1:
        raise Mt5ReportError("MT5 report Deals section is missing or ambiguous.")
    header_index = sections[0] + 1
    if header_index >= len(rows) or rows[header_index] != _DEALS_HEADER:
        raise Mt5ReportError("MT5 report Deals layout is unsupported.")

    events: list[dict[str, str]] = []
    final_balance: str | None = None
    for row in rows[header_index + 1 :]:
        if len(row) == len(_DEALS_HEADER) and final_balance is None:
            events.append(_parse_deal_event(row))
        elif len(row) == 6 and row[0] == row[-1] == "" and final_balance is None:
            _parse_money(row[1])
            _parse_money(row[2])
            _parse_money(row[3])
            final_balance = _parse_money(row[4])
        else:
            raise Mt5ReportError("MT5 report Deals row is unsupported.")

    if not events or final_balance is None:
        raise Mt5ReportError("MT5 report Deals section is incomplete.")
    identifiers = tuple(event["source_record_id"] for event in events)
    if len(set(identifiers)) != len(identifiers):
        raise Mt5ReportError("MT5 report Deals ordering is ambiguous.")
    if events[0]["direction"] != "balance" or any(
        event["direction"] == "balance" for event in events[1:]
    ):
        raise Mt5ReportError("MT5 report initial balance event is unsupported.")
    if events[-1]["balance"] != final_balance:
        raise Mt5ReportError("MT5 report final balance is contradictory.")
    return tuple(events), final_balance


def _parse_deal_event(row: tuple[str, ...]) -> dict[str, str]:
    (
        local_time,
        source_record_id,
        instrument,
        event_type,
        direction,
        volume,
        price,
        related_order_id,
        commission,
        swap,
        profit,
        balance,
        _comment,
    ) = row
    parsed_time = _parse_local_time(local_time)
    if not source_record_id:
        raise Mt5ReportError("MT5 report source record identifier is invalid.")
    parsed_commission = _parse_money(commission)
    parsed_swap = _parse_money(swap)
    parsed_profit = _parse_money(profit)
    parsed_balance = _parse_money(balance)

    if event_type == "balance":
        if any((instrument, direction, volume, price, related_order_id)):
            raise Mt5ReportError("MT5 report balance event is unsupported.")
        return {
            "source_record_id": source_record_id,
            "local_time": parsed_time,
            "direction": "balance",
            "commission": parsed_commission,
            "swap": parsed_swap,
            "profit": parsed_profit,
            "balance": parsed_balance,
        }

    if (
        event_type not in {"buy", "sell"}
        or direction not in {"in", "out"}
        or not instrument
        or not related_order_id
    ):
        raise Mt5ReportError("MT5 report execution event is unsupported.")
    if direction == "in" and parsed_profit != "0.00":
        raise Mt5ReportError("MT5 report entry event profit is contradictory.")
    return {
        "source_record_id": source_record_id,
        "local_time": parsed_time,
        "instrument": instrument,
        "side": event_type,
        "direction": direction,
        "volume": _parse_unsigned_decimal(volume),
        "price": _parse_unsigned_decimal(price),
        "related_order_id": related_order_id,
        "commission": parsed_commission,
        "swap": parsed_swap,
        "profit": parsed_profit,
        "balance": parsed_balance,
    }


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


def _parse_unsigned_decimal(value: str) -> str:
    if _UNSIGNED_DECIMAL.fullmatch(value) is None:
        raise Mt5ReportError("MT5 report decimal value is unsupported.")
    try:
        amount = Decimal(value)
    except InvalidOperation as error:
        raise Mt5ReportError("MT5 report decimal value is invalid.") from error
    if amount == 0:
        amount = abs(amount)
    normalized = format(amount, "f").rstrip("0").rstrip(".")
    return f"{normalized}.0" if "." not in normalized else normalized


def _parse_local_time(value: str) -> str:
    try:
        parsed = datetime.strptime(value, _LOCAL_TIME)
    except ValueError as error:
        raise Mt5ReportError("MT5 report local time is unsupported.") from error
    if parsed.strftime(_LOCAL_TIME) != value:
        raise Mt5ReportError("MT5 report local time is unsupported.")
    return parsed.isoformat(timespec="seconds")


def _parse_count(value: str) -> int:
    if re.fullmatch(r"[0-9]+", value) is None:
        raise Mt5ReportError("MT5 report trade count is invalid.")
    return int(value)


def _parse_count_with_percent(value: str) -> int:
    match = _COUNT_WITH_PERCENT.fullmatch(value)
    if match is None:
        raise Mt5ReportError("MT5 report trade count is invalid.")
    return int(match.group(1))
