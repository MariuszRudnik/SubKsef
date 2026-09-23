from decimal import Decimal, InvalidOperation

from subksef.invoice.epp import CatalogItem
from subksef.invoice.fa3 import LineItem


def is_missing(line: LineItem, goods: tuple[CatalogItem, ...] | list[CatalogItem]) -> bool:
    code = line.index.strip().casefold()
    if code and any(item.code.strip().casefold() == code for item in goods):
        return False
    return suggest_good(line, goods) is None


def missing_lines(
    lines: tuple[LineItem, ...] | list[LineItem],
    goods: tuple[CatalogItem, ...] | list[CatalogItem],
) -> tuple[LineItem, ...]:
    missing = []
    seen = set()
    for line in lines:
        if not is_missing(line, goods):
            continue
        name, price = _line_name_price(line)
        key = (line.index.strip().casefold(), name, price)
        if key in seen:
            continue
        seen.add(key)
        missing.append(line)
    return tuple(missing)


def code_in_catalog(line: LineItem, goods: tuple[CatalogItem, ...] | list[CatalogItem]) -> bool:
    code = line.index.strip().casefold()
    if not code:
        return False
    return any(item.code.strip().casefold() == code for item in goods)


def suggest_good(line: LineItem, goods: tuple[CatalogItem, ...] | list[CatalogItem]) -> CatalogItem | None:
    invoice_name, invoice_price = _line_name_price(line)
    if not invoice_name or invoice_price is None:
        return None
    if code_in_catalog(line, goods):
        return None
    best: tuple[int, str, CatalogItem] | None = None
    for item in goods:
        stem, price = _catalog_name_price(item)
        if price != invoice_price:
            continue
        rank = _name_rank(invoice_name, stem)
        if rank is None:
            continue
        if item.code.strip().casefold() == line.index.strip().casefold():
            continue
        candidate = (rank, item.code.casefold(), item)
        if best is None or candidate < best:
            best = candidate
    if best is None:
        return None
    return best[2]


def _catalog_name_price(item: CatalogItem) -> tuple[str, Decimal | None]:
    stem, embedded = _split_name(item.name)
    if embedded is not None:
        return stem, embedded
    listed = _parse_price(item.net_price)
    if listed is not None and listed != 0:
        return stem, listed
    return stem, None


def _name_rank(invoice_name: str, catalog_name: str) -> int | None:
    if invoice_name == catalog_name:
        return 0
    invoice_words = invoice_name.split()
    catalog_words = catalog_name.split()
    if len(invoice_name) >= 4 and invoice_name in catalog_words:
        return 1
    if len(catalog_name) >= 4 and catalog_name in invoice_words:
        return 1
    return None


def _line_name_price(line: LineItem) -> tuple[str, Decimal | None]:
    price = _parse_price(line.price_after_discount) or _parse_price(line.unit_price)
    stem, _embedded = _split_name(line.name)
    return stem, price


def _split_name(name: str) -> tuple[str, Decimal | None]:
    folded = _fold(name)
    stem, separator, tail = folded.rpartition(" ")
    if not separator:
        return folded, None
    price = _parse_price(tail)
    if price is None:
        return folded, None
    return stem, price


def _parse_price(value: str) -> Decimal | None:
    text = value.strip().replace(" ", "").replace(",", ".")
    if not text:
        return None
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def _fold(value: str) -> str:
    return " ".join(value.casefold().split())
