import csv
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path

from subksef.invoice.fa3 import Invoice, InvoiceReadError, LineItem, Party, unit_discount

DOCUMENT_TYPES = frozenset(
    {
        "FZ",
        "FR",
        "FS",
        "RZ",
        "RS",
        "KFZ",
        "KFS",
        "KRZ",
        "KRS",
        "MMW",
        "PZ",
        "WZ",
        "VPZ",
        "VWZ",
        "PW",
        "RW",
        "ZW",
        "ZD",
        "ZK",
        "PA",
        "FM",
        "KFM",
    }
)
PURCHASE_TYPES = frozenset({"FZ", "FR", "RZ", "KFZ", "KRZ", "PZ", "VPZ", "ZD"})


@dataclass(frozen=True)
class CatalogItem:
    code: str
    name: str
    net_price: str
    gross_price: str


def read_catalog(path: str | Path) -> tuple[CatalogItem, ...]:
    try:
        rows = _read_rows(path)
    except OSError as error:
        raise InvoiceReadError("Nie udało się odczytać pliku EPP.") from error

    sections = _sections(rows)
    if _first(sections, "INFO") is None:
        raise InvoiceReadError("Ten plik nie jest plikiem EPP Subiekta.")

    goods_rows = _content(sections, "TOWARY")
    if not goods_rows:
        raise InvoiceReadError("W pliku EPP nie ma kartoteki towarów.")

    prices = _prices(_content(sections, "CENNIK"))
    items = []
    for row in goods_rows:
        code = _field(row, 1)
        if not code:
            continue
        net_price, gross_price = prices.get(code, ("", ""))
        items.append(
            CatalogItem(
                code=code,
                name=_field(row, 4),
                net_price=net_price,
                gross_price=gross_price,
            )
        )
    if not items:
        raise InvoiceReadError("W pliku EPP nie ma towarów z kodem.")
    return tuple(items)


def read_epp(path: str | Path) -> tuple[Invoice, ...]:
    try:
        rows = _read_rows(path)
    except OSError as error:
        raise InvoiceReadError("Nie udało się odczytać pliku EPP.") from error

    sections = _sections(rows)
    info = _first(sections, "INFO")
    if info is None:
        raise InvoiceReadError("Ten plik nie jest plikiem EPP Subiekta.")

    goods = {
        _field(row, 1): row
        for row in _content(sections, "TOWARY")
        if _field(row, 1)
    }
    own = _own_party(info)
    documents = []
    for header, lines in _documents(sections):
        documents.append(_invoice(header, lines, own, goods))
    if not documents:
        raise InvoiceReadError("W pliku EPP nie ma dokumentu.")
    return tuple(documents)


def _read_rows(path: str | Path) -> list[list[str]]:
    raw = Path(path).read_bytes()
    text = raw.decode("cp1250")
    rows = _parse(text)
    info = _first(_sections(rows), "INFO")
    if info is not None and _field(info, 2) == "852":
        rows = _parse(raw.decode("cp852"))
    return rows


def _parse(text: str) -> list[list[str]]:
    return list(csv.reader(text.splitlines(), delimiter=",", quotechar='"'))


def _sections(rows: list[list[str]]) -> list[tuple[str, list[list[str]]]]:
    sections: list[tuple[str, list[list[str]]]] = []
    name = ""
    bucket: list[list[str]] = []
    for row in rows:
        if len(row) == 1 and row[0].startswith("[") and row[0].endswith("]"):
            if name:
                sections.append((name, bucket))
            name = row[0][1:-1]
            bucket = []
        elif row and name:
            bucket.append(row)
    if name:
        sections.append((name, bucket))
    return sections


def _first(sections: list[tuple[str, list[list[str]]]], label: str) -> list[str] | None:
    for name, rows in sections:
        if name == label and rows:
            return rows[0]
    return None


def _prices(rows: list[list[str]]) -> dict[str, tuple[str, str]]:
    chosen: dict[str, tuple[str, str, bool]] = {}
    for row in rows:
        code = _field(row, 0)
        if not code:
            continue
        retail = _field(row, 1).casefold() == "detaliczna"
        current = chosen.get(code)
        if current is None or (retail and not current[2]):
            chosen[code] = (_amount(_field(row, 2)), _amount(_field(row, 3)), retail)
    return {code: (net, gross) for code, (net, gross, _retail) in chosen.items()}


def _content(sections: list[tuple[str, list[list[str]]]], kind: str) -> list[list[str]]:
    pending = ""
    for name, rows in sections:
        if name == "NAGLOWEK" and rows:
            pending = rows[0][0]
        elif name == "ZAWARTOSC" and pending == kind:
            return rows
    return []


def _documents(
    sections: list[tuple[str, list[list[str]]]],
) -> list[tuple[list[str], list[list[str]]]]:
    pending: list[str] | None = None
    found = []
    for name, rows in sections:
        if name == "NAGLOWEK" and rows:
            pending = rows[0]
        elif name == "ZAWARTOSC" and pending and pending[0] in DOCUMENT_TYPES:
            found.append((pending, rows))
            pending = None
    return found


def _invoice(
    header: list[str],
    lines: list[list[str]],
    own: Party,
    goods: dict[str, list[str]],
) -> Invoice:
    kind = _field(header, 0)
    number = _field(header, 6) or _field(header, 3)
    if number and not number.startswith(kind):
        number = f"{kind} {number}"
    contractor = Party(
        name=_field(header, 13) or _field(header, 12),
        nip=_field(header, 17),
        address=_address(
            _field(header, 16),
            _field(header, 15),
            _field(header, 14),
            _field(header, 59),
        ),
    )
    seller, buyer = (contractor, own) if kind in PURCHASE_TYPES else (own, contractor)
    return Invoice(
        number=number,
        issue_date=_date(_field(header, 21)),
        delivery_date=_date(_field(header, 22)),
        payment_due=_date(_field(header, 34)),
        seller=seller,
        buyer=buyer,
        net=_amount(_field(header, 27)),
        vat=_amount(_field(header, 28)),
        gross=_amount(_field(header, 29)),
        currency=_field(header, 46),
        payment_form=_field(header, 33),
        lines=tuple(_line(row, goods) for row in lines),
    )


def _line(row: list[str], goods: dict[str, list[str]]) -> LineItem:
    code = _field(row, 2)
    product = goods.get(code, [])
    name = _field(product, 4) or _field(row, 21) or code
    unit_price = _field(row, 13)
    quantity = _field(row, 10)
    net_value = _field(row, 16)
    after, discount_value = unit_discount(
        unit_price,
        quantity,
        net_value,
        discount_amount=_field(row, 7),
        discount_percent=_field(row, 8),
    )
    return LineItem(
        number=_field(row, 0),
        name=name,
        index=code,
        gtin=_field(product, 3),
        unit=_field(row, 9),
        quantity=_quantity(quantity),
        unit_price=_amount(unit_price),
        net_value=_amount(net_value),
        vat_rate=_quantity(_field(row, 15)),
        price_after_discount=after,
        discount_amount=discount_value,
    )


def _own_party(info: list[str]) -> Party:
    return Party(
        name=_field(info, 6) or _field(info, 5),
        nip=_field(info, 10),
        address=_address(
            _field(info, 9),
            _field(info, 8),
            _field(info, 7),
            _field(info, 20),
        ),
    )


def _address(street: str, postal: str, city: str, country: str) -> str:
    locality = " ".join(part for part in (postal, city) if part)
    return ", ".join(part for part in (street, locality, country) if part)


def _date(value: str) -> str:
    if len(value) >= 8 and value[:8].isdigit():
        return f"{value[0:4]}-{value[4:6]}-{value[6:8]}"
    return value


def _amount(value: str) -> str:
    if not value:
        return ""
    try:
        number = Decimal(value).quantize(Decimal("0.01"))
    except InvalidOperation:
        return value
    return f"{number:,.2f}".replace(",", " ").replace(".", ",")


def _quantity(value: str) -> str:
    if not value:
        return ""
    try:
        number = Decimal(value)
    except InvalidOperation:
        return value
    if number == number.to_integral():
        return str(int(number))
    return format(number.normalize(), "f").replace(".", ",")


def _field(row: list[str], index: int) -> str:
    if index >= len(row):
        return ""
    return row[index].strip()
