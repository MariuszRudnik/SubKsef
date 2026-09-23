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


def suggest_good(line: LineItem, goods: tuple[CatalogItem, ...] | list[CatalogItem]) -> CatalogItem | None:
    invoice_name, invoice_price = _line_name_price(line)
    if not invoice_name:
        return None
    ordered = sorted(goods, key=lambda item: item.code.casefold())
    current = _by_code(ordered).get(line.index.strip().casefold())
    if current is not None and _same_product(current, invoice_name, invoice_price):
        return None
    if invoice_price is None:
        return None
    for item in ordered:
        stem, price = _split_name(item.name)
        if stem != invoice_name or price != invoice_price:
            continue
        if item.code.strip().casefold() == line.index.strip().casefold():
            return None
        return item
    return None


def _by_code(goods: list[CatalogItem]) -> dict[str, CatalogItem]:
    found = {}
    for item in goods:
        found.setdefault(item.code.strip().casefold(), item)
    return found


def _same_product(item: CatalogItem, invoice_name: str, invoice_price: Decimal | None) -> bool:
    if _fold(item.name) == invoice_name:
        return True
    stem, price = _split_name(item.name)
    if stem != invoice_name:
        return False
    return invoice_price is None or price is None or price == invoice_price


def _line_name_price(line: LineItem) -> tuple[str, Decimal | None]:
    price = _parse_price(line.unit_price)
    stem, embedded = _split_name(line.name)
    if embedded is not None and (price is None or embedded == price):
        return stem, price if price is not None else embedded
    folded = _fold(line.name)
    return folded, price


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
