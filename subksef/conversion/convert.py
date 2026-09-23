import csv
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
import xml.etree.ElementTree as ET

from subksef.invoice.epp import DOCUMENT_TYPES, PURCHASE_TYPES, read_epp
from subksef.invoice.fa3 import PAYMENT_FORMS, Invoice, InvoiceReadError, LineItem, read_invoice

FA_NAMESPACE = "http://crd.gov.pl/wzor/2025/06/25/13775/"
ET.register_namespace("", FA_NAMESPACE)

PAYMENT_CODES = {name: code for code, name in PAYMENT_FORMS.items()}


def target_suffix(source: Path) -> str:
    if source.suffix.lower() == ".xml":
        return ".epp"
    if source.suffix.lower() == ".epp":
        return ".xml"
    return source.suffix


def suggested_target(source: Path) -> Path:
    return source.with_name(f"{source.stem}-wynik{target_suffix(source)}")


def output_paths(source: Path, target: Path) -> tuple[Path, ...]:
    suffix = source.suffix.lower()
    if suffix == ".xml":
        return (_with_suffix(target, ".epp"),)
    if suffix == ".epp":
        destination = _with_suffix(target, ".xml")
        return tuple(_split_targets(destination, len(read_epp(source))))
    raise InvoiceReadError("Konwersja obsługuje pliki XML i EPP.")


def convert(source: Path, target: Path) -> tuple[Path, ...]:
    suffix = source.suffix.lower()
    if suffix == ".xml":
        destination = _with_suffix(target, ".epp")
        write_epp((read_invoice(source),), destination)
        return (destination,)
    if suffix == ".epp":
        destination = _with_suffix(target, ".xml")
        invoices = read_epp(source)
        paths = _split_targets(destination, len(invoices))
        for invoice, path in zip(invoices, paths, strict=True):
            write_fa(invoice, path)
        return tuple(paths)
    raise InvoiceReadError("Konwersja obsługuje pliki XML i EPP.")


def write_epp(invoices: tuple[Invoice, ...], path: Path) -> None:
    if not invoices:
        raise InvoiceReadError("Brak dokumentu do zapisania.")
    kind, _number = _document_identity(invoices[0])
    own = invoices[0].buyer if kind in PURCHASE_TYPES else invoices[0].seller
    rows: list[list[str]] = [["[INFO]"], _info_row(own)]
    goods: list[tuple[str, LineItem]] = []
    seen: set[str] = set()
    for invoice in invoices:
        document_kind, number = _document_identity(invoice)
        contractor = invoice.seller if document_kind in PURCHASE_TYPES else invoice.buyer
        rows.append(["[NAGLOWEK]"])
        rows.append(_document_row(invoice, document_kind, number, contractor))
        rows.append(["[ZAWARTOSC]"])
        for line in invoice.lines:
            code = _goods_code(line.index, line.number)
            rows.append(_line_row(line, code))
            if code not in seen:
                seen.add(code)
                goods.append((code, line))
    rows.append(["[NAGLOWEK]"])
    rows.append(["TOWARY"])
    rows.append(["[ZAWARTOSC]"])
    for code, line in goods:
        rows.append(["1", code, "", line.gtin, line.name, "", line.name])
    _write_csv(path, rows)


def write_fa(invoice: Invoice, path: Path) -> None:
    root = ET.Element(f"{{{FA_NAMESPACE}}}Faktura")
    header = _fa(root, "Naglowek")
    _fa(
        header,
        "KodFormularza",
        "FA",
        kodSystemowy="FA (3)",
        wersjaSchemy="1-0E",
    )
    _fa(header, "WariantFormularza", "3")
    _fa(header, "DataWytworzeniaFa", datetime.now().strftime("%Y-%m-%dT%H:%M:%S"))
    _fa(header, "SystemInfo", "Subksef")
    _party(root, "Podmiot1", invoice.seller, buyer=False)
    _party(root, "Podmiot2", invoice.buyer, buyer=True)

    fa = _fa(root, "Fa")
    _fa(fa, "KodWaluty", invoice.currency or "PLN")
    _fa(fa, "P_1", invoice.issue_date)
    _fa(fa, "P_2", invoice.number)
    _fa(fa, "P_6", invoice.delivery_date)
    _fa(fa, "P_13_1", _xml_amount(invoice.net))
    _fa(fa, "P_14_1", _xml_amount(invoice.vat))
    _fa(fa, "P_15", _xml_amount(invoice.gross))
    notes = _fa(fa, "Adnotacje")
    _fa(notes, "P_16", "2")
    _fa(notes, "P_17", "2")
    _fa(notes, "P_18", "2")
    _fa(notes, "P_18A", "2")
    _fa(_fa(notes, "Zwolnienie"), "P_19N", "1")
    _fa(_fa(notes, "NoweSrodkiTransportu"), "P_22N", "1")
    _fa(notes, "P_23", "2")
    _fa(_fa(notes, "PMarzy"), "P_PMarzyN", "1")
    _fa(fa, "RodzajFaktury", "VAT")
    for line in invoice.lines:
        row = _fa(fa, "FaWiersz")
        _fa(row, "NrWierszaFa", line.number)
        _fa(row, "P_7", line.name)
        _fa(row, "Indeks", line.index)
        _fa(row, "GTIN", line.gtin)
        _fa(row, "P_8A", line.unit)
        _fa(row, "P_8B", _plain(line.quantity))
        _fa(row, "P_9A", _xml_amount(line.unit_price))
        _fa(row, "P_11", _xml_amount(line.net_value))
        _fa(row, "P_12", _plain(line.vat_rate))
    if invoice.payment_due or invoice.payment_form:
        payment = _fa(fa, "Platnosc")
        if invoice.payment_due:
            _fa(_fa(payment, "TerminPlatnosci"), "Termin", invoice.payment_due)
        code = PAYMENT_CODES.get(invoice.payment_form)
        if code:
            _fa(payment, "FormaPlatnosci", code)

    path.parent.mkdir(parents=True, exist_ok=True)
    tree = ET.ElementTree(root)
    ET.indent(tree, space="  ")
    tree.write(path, encoding="utf-8", xml_declaration=True)


def _party(root: ET.Element, tag: str, party, buyer: bool) -> None:
    element = _fa(root, tag)
    identity = _fa(element, "DaneIdentyfikacyjne")
    _fa(identity, "NIP", _digits(party.nip) or party.nip)
    _fa(identity, "Nazwa", party.name)
    country, line = _split_country(party.address)
    address = _fa(element, "Adres")
    _fa(address, "KodKraju", country)
    _fa(address, "AdresL1", line)
    if buyer:
        _fa(element, "JST", "2")
        _fa(element, "GV", "2")


def _info_row(party) -> list[str]:
    row = [""] * 24
    row[0] = "1.11"
    row[1] = "3"
    row[2] = "1250"
    row[3] = "Subksef"
    row[4] = (_digits(party.nip) or party.name)[:20]
    row[5] = party.name[:40]
    row[6] = party.name
    row[9] = party.address
    row[10] = party.nip
    row[15] = "0"
    row[18] = "Subksef"
    row[19] = datetime.now().strftime("%Y%m%d%H%M%S")
    row[23] = "0"
    return row


def _document_row(invoice: Invoice, kind: str, number: str, contractor) -> list[str]:
    row = [""] * 62
    row[0] = kind
    row[1] = "1"
    row[3] = number
    row[6] = number
    row[11] = (_digits(contractor.nip) or contractor.name)[:20]
    row[12] = contractor.name[:40]
    row[13] = contractor.name
    row[16] = contractor.address
    row[17] = contractor.nip
    row[21] = _epp_date(invoice.issue_date)
    row[22] = _epp_date(invoice.delivery_date)
    row[23] = _epp_date(invoice.delivery_date)
    row[24] = str(len(invoice.lines))
    row[25] = "1"
    row[27] = _epp_amount(invoice.net)
    row[28] = _epp_amount(invoice.vat)
    row[29] = _epp_amount(invoice.gross)
    row[30] = _epp_amount(invoice.net)
    row[33] = invoice.payment_form
    row[34] = _epp_date(invoice.payment_due)
    row[35] = "0.0000"
    row[36] = _epp_amount(invoice.gross)
    row[39] = "1"
    row[46] = invoice.currency or "PLN"
    row[47] = "1.0000"
    row[61] = "0"
    return row


def _line_row(line, code: str) -> list[str]:
    net = _money(line.net_value)
    rate = _money(line.vat_rate)
    vat = (net * rate / Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    gross = net + vat
    unit_net = _money(line.unit_price)
    unit_gross = (unit_net * (Decimal("1") + rate / Decimal("100"))).quantize(
        Decimal("0.0001"),
        rounding=ROUND_HALF_UP,
    )
    row = [""] * 22
    row[0] = line.number or "0"
    row[1] = "1"
    row[2] = code
    row[3] = "1"
    row[4] = "1"
    row[5] = "0"
    row[6] = "1"
    row[7] = "0.0000"
    row[8] = "0.0000"
    row[9] = line.unit or "szt."
    row[10] = _epp_amount(_plain(line.quantity) or "0")
    row[11] = row[10]
    row[12] = "0.0000"
    row[13] = _epp_amount(line.unit_price)
    row[14] = _four(unit_gross)
    row[15] = _epp_amount(line.vat_rate)
    row[16] = _epp_amount(line.net_value)
    row[17] = _four(vat)
    row[18] = _four(gross)
    row[19] = _epp_amount(line.net_value)
    return row


def _document_identity(invoice: Invoice) -> tuple[str, str]:
    parts = invoice.number.split(" ", 1)
    if len(parts) == 2 and parts[0] in DOCUMENT_TYPES:
        return parts[0], parts[1]
    return "FS", invoice.number


def _goods_code(index: str, number: str) -> str:
    code = index.strip() or f"P{number or '0'}"
    return code[:20]


def _write_csv(path: Path, rows: list[list[str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    for row in rows:
        if len(row) == 1 and row[0].startswith("[") and row[0].endswith("]"):
            lines.append(row[0])
            continue
        buffer = csv.StringIO(newline="")
        csv.writer(
            buffer,
            delimiter=",",
            quotechar='"',
            lineterminator="",
            quoting=csv.QUOTE_MINIMAL,
        ).writerow(row)
        lines.append(buffer.getvalue())
    text = "\r\n".join(lines) + "\r\n"
    path.write_bytes(text.encode("cp1250", errors="replace"))


def _fa(parent: ET.Element, name: str, text: str = "", **attrs: str) -> ET.Element:
    element = ET.SubElement(parent, f"{{{FA_NAMESPACE}}}{name}", attrs)
    if text:
        element.text = text
    return element


def _split_country(address: str) -> tuple[str, str]:
    for suffix in (", PL", ", Polska"):
        if address.endswith(suffix):
            return "PL", address[: -len(suffix)].rstrip(", ")
    return "PL", address


def _split_targets(path: Path, count: int) -> list[Path]:
    if count <= 1:
        return [path]
    return [
        path.with_name(f"{path.stem}-{index}{path.suffix}")
        for index in range(1, count + 1)
    ]


def _with_suffix(path: Path, suffix: str) -> Path:
    if path.suffix.lower() == suffix:
        return path
    return path.with_suffix(suffix)


def _epp_date(value: str) -> str:
    digits = value.replace("-", "")
    if len(digits) >= 8 and digits[:8].isdigit():
        return f"{digits[:8]}000000"
    return ""


def _money(value: str) -> Decimal:
    if not value:
        return Decimal("0")
    try:
        return Decimal(value.replace(" ", "").replace(",", "."))
    except InvalidOperation:
        return Decimal("0")


def _xml_amount(value: str) -> str:
    if not value:
        return ""
    amount = _money(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return f"{amount:.2f}"


def _epp_amount(value: str) -> str:
    return _four(_money(value))


def _four(value: Decimal) -> str:
    amount = value.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
    return f"{amount:.4f}"


def _plain(value: str) -> str:
    return value.replace(" ", "").replace(",", ".")


def _digits(value: str) -> str:
    return "".join(character for character in value if character.isdigit())
