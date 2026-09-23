from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
import xml.etree.ElementTree as ET

NET_FIELDS = (
    "P_13_1",
    "P_13_2",
    "P_13_3",
    "P_13_4",
    "P_13_5",
    "P_13_6_1",
    "P_13_6_2",
    "P_13_6_3",
    "P_13_7",
    "P_13_8",
    "P_13_9",
    "P_13_10",
    "P_13_11",
)
VAT_FIELDS = ("P_14_1", "P_14_2", "P_14_3", "P_14_4", "P_14_5")
PAYMENT_FORMS = {
    "1": "gotówka",
    "2": "karta",
    "3": "bon",
    "4": "czek",
    "5": "kredyt",
    "6": "przelew",
    "7": "mobilna",
}


class InvoiceReadError(Exception):
    pass


@dataclass(frozen=True)
class Party:
    name: str
    nip: str
    address: str


@dataclass(frozen=True)
class LineItem:
    number: str
    name: str
    index: str
    gtin: str
    unit: str
    quantity: str
    unit_price: str
    net_value: str
    vat_rate: str


@dataclass(frozen=True)
class Invoice:
    number: str
    issue_date: str
    delivery_date: str
    payment_due: str
    seller: Party
    buyer: Party
    net: str
    vat: str
    gross: str
    currency: str
    payment_form: str
    lines: tuple[LineItem, ...]


def read_invoice(path: str | Path) -> Invoice:
    try:
        root = ET.parse(path).getroot()
    except (ET.ParseError, OSError) as error:
        raise InvoiceReadError("Nie udało się odczytać pliku XML.") from error

    if _local(root.tag) != "Faktura":
        raise InvoiceReadError("Ten plik nie jest fakturą FA.")

    header = _child(root, "Naglowek")
    form_code = _text(header, "KodFormularza") if header is not None else ""
    if form_code != "FA":
        raise InvoiceReadError("Ten plik nie jest fakturą FA.")

    invoice = _child(root, "Fa")
    if invoice is None:
        raise InvoiceReadError("W pliku brakuje danych faktury.")

    payment = _child(invoice, "Platnosc")
    return Invoice(
        number=_text(invoice, "P_2"),
        issue_date=_text(invoice, "P_1"),
        delivery_date=_text(invoice, "P_6"),
        payment_due=_payment_due(payment),
        seller=_party(_child(root, "Podmiot1")),
        buyer=_party(_child(root, "Podmiot2")),
        net=_sum_fields(invoice, NET_FIELDS),
        vat=_sum_fields(invoice, VAT_FIELDS),
        gross=_amount(_text(invoice, "P_15")),
        currency=_text(invoice, "KodWaluty"),
        payment_form=_payment_form(payment),
        lines=tuple(_line(row) for row in _children(invoice, "FaWiersz")),
    )


def _party(element: ET.Element | None) -> Party:
    identity = _child(element, "DaneIdentyfikacyjne")
    address = _child(element, "Adres")
    lines = [
        _text(address, "AdresL1"),
        _text(address, "AdresL2"),
    ]
    country = _text(address, "KodKraju")
    if country:
        lines.append(country)
    return Party(
        name=_text(identity, "Nazwa"),
        nip=_text(identity, "NIP"),
        address=", ".join(line for line in lines if line),
    )


def _line(row: ET.Element) -> LineItem:
    return LineItem(
        number=_text(row, "NrWierszaFa"),
        name=_text(row, "P_7"),
        index=_text(row, "Indeks"),
        gtin=_text(row, "GTIN"),
        unit=_text(row, "P_8A"),
        quantity=_text(row, "P_8B"),
        unit_price=_amount(_text(row, "P_9A")),
        net_value=_amount(_text(row, "P_11")),
        vat_rate=_text(row, "P_12"),
    )


def _payment_due(payment: ET.Element | None) -> str:
    term = _child(payment, "TerminPlatnosci")
    return _text(term, "Termin")


def _payment_form(payment: ET.Element | None) -> str:
    code = _text(payment, "FormaPlatnosci")
    if not code:
        return ""
    return PAYMENT_FORMS.get(code, code)


def _sum_fields(element: ET.Element, names: tuple[str, ...]) -> str:
    total = Decimal("0")
    found = False
    for name in names:
        raw = _text(element, name)
        if not raw:
            continue
        try:
            total += Decimal(raw)
        except InvalidOperation:
            continue
        found = True
    if not found:
        return ""
    return _amount(str(total))


def _amount(value: str) -> str:
    if not value:
        return ""
    try:
        number = Decimal(value).quantize(Decimal("0.01"))
    except InvalidOperation:
        return value
    text = f"{number:,.2f}"
    return text.replace(",", " ").replace(".", ",")


def _text(element: ET.Element | None, name: str) -> str:
    child = _child(element, name)
    if child is None or child.text is None:
        return ""
    return child.text.strip()


def _child(element: ET.Element | None, name: str) -> ET.Element | None:
    if element is None:
        return None
    for child in element:
        if _local(child.tag) == name:
            return child
    return None


def _children(element: ET.Element, name: str) -> list[ET.Element]:
    return [child for child in element if _local(child.tag) == name]


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]
