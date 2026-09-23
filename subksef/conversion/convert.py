from dataclasses import replace
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
import xml.etree.ElementTree as ET

from subksef.catalog.store import list_replacements
from subksef.invoice.epp import DOCUMENT_TYPES, PURCHASE_TYPES, CatalogItem, read_epp
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


def convert(
    source: Path,
    target: Path,
    replacements: dict[tuple[int, int], CatalogItem] | None = None,
    use_discounted_price: bool = True,
) -> tuple[Path, ...]:
    suffix = source.suffix.lower()
    if suffix == ".xml":
        destination = _with_suffix(target, ".epp")
        loaded = (read_invoice(source),)
        invoices = with_replacements(loaded, _mapping(loaded, replacements))
        if use_discounted_price:
            invoices = _discounted_unit_prices(invoices)
        write_epp(invoices, destination)
        return (destination,)
    if suffix == ".epp":
        destination = _with_suffix(target, ".xml")
        loaded = read_epp(source)
        invoices = with_replacements(loaded, _mapping(loaded, replacements))
        if use_discounted_price:
            invoices = _discounted_unit_prices(invoices)
        paths = _split_targets(destination, len(invoices))
        for invoice, path in zip(invoices, paths, strict=True):
            write_fa(invoice, path)
        return tuple(paths)
    raise InvoiceReadError("Konwersja obsługuje pliki XML i EPP.")


def _discounted_unit_prices(invoices: tuple[Invoice, ...]) -> tuple[Invoice, ...]:
    changed = []
    for invoice in invoices:
        lines = []
        for line in invoice.lines:
            price = line.price_after_discount or line.unit_price
            if price and price != line.unit_price:
                lines.append(replace(line, unit_price=price))
            else:
                lines.append(line)
        changed.append(replace(invoice, lines=tuple(lines)))
    return tuple(changed)


def _mapping(
    invoices: tuple[Invoice, ...],
    replacements: dict[tuple[int, int], CatalogItem] | None,
) -> dict[tuple[int, int], CatalogItem]:
    mapping: dict[tuple[int, int], CatalogItem] = {}
    for doc_index, invoice in enumerate(invoices):
        for line_index, item in list_replacements(invoice.number, doc_index).items():
            mapping[(doc_index, line_index)] = item
    if replacements:
        mapping.update(replacements)
    return mapping


def with_replacements(
    invoices: tuple[Invoice, ...],
    replacements: dict[tuple[int, int], CatalogItem] | None,
) -> tuple[Invoice, ...]:
    if not replacements:
        return invoices
    changed = []
    for doc_index, invoice in enumerate(invoices):
        lines = []
        touched = False
        for line_index, line in enumerate(invoice.lines):
            item = replacements.get((doc_index, line_index))
            if item is None:
                lines.append(line)
                continue
            touched = True
            lines.append(replace(line, name=item.name, index=item.code))
        changed.append(replace(invoice, lines=tuple(lines)) if touched else invoice)
    return tuple(changed)


def write_epp(invoices: tuple[Invoice, ...], path: Path) -> None:
    if not invoices:
        raise InvoiceReadError("Brak dokumentu do zapisania.")
    kind, _number = _document_identity(invoices[0])
    own = invoices[0].buyer if kind in PURCHASE_TYPES else invoices[0].seller
    blocks: list[str] = [_section("[INFO]", [_info_row(own)], INFO_TEXT)]

    contractors: dict[str, object] = {}
    goods: dict[str, LineItem] = {}
    endings: list[tuple[str, str]] = []
    for invoice in invoices:
        document_kind, number = _document_identity(invoice)
        contractor = invoice.seller if document_kind in PURCHASE_TYPES else invoice.buyer
        code = _party_code(contractor)
        contractors.setdefault(code, contractor)
        line_rows = []
        for line in invoice.lines:
            goods_code = _goods_code(line.index, line.number)
            line_rows.append(_line_row(line, goods_code))
            goods.setdefault(goods_code, line)
        blocks.append(_section("[NAGLOWEK]", [_document_row(invoice, document_kind, number, code, contractor)], DOCUMENT_TEXT))
        blocks.append(_section("[ZAWARTOSC]", line_rows, LINE_TEXT))
        endings.append((f"{document_kind} {number[:30]}", _epp_date(invoice.delivery_date or invoice.issue_date)))

    blocks.extend(_catalog(contractors, goods, endings))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes("".join(blocks).encode("cp1250", errors="replace"))


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


INFO_TEXT = {0, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 18, 20, 21, 22}
DOCUMENT_TEXT = {
    0, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 26, 31, 33,
    41, 42, 43, 46, 48, 49, 50, 51, 55, 57, 59, 60,
}
LINE_TEXT = {2, 9, 20, 21}
CONTRACTOR_TEXT = {1, 2, 3, 4, 5, 6, 7, 8, 27, 28}
GOODS_TEXT = {1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 12, 16, 18, 19, 20, 26, 29, 31}


def _info_row(party) -> list[str]:
    street, postal, city = _split_address(party.address)
    row = [""] * 24
    row[0] = "1.11"
    row[1] = "1"
    row[2] = "1250"
    row[3] = "Subksef"
    row[4] = _party_code(party)
    row[5] = party.name[:40]
    row[6] = party.name[:80]
    row[7] = city
    row[8] = postal
    row[9] = street
    row[10] = party.nip
    row[15] = "0"
    row[18] = "Subksef"
    row[19] = datetime.now().strftime("%Y%m%d%H%M%S")
    row[20] = "Polska"
    row[21] = "PL"
    row[23] = "0"
    return row


def _document_row(invoice: Invoice, kind: str, number: str, code: str, contractor) -> list[str]:
    street, postal, city = _split_address(contractor.address)
    row = [""] * 62
    row[0] = kind
    row[1] = "1"
    row[2] = "0"
    row[3] = _doc_number(number)
    row[6] = number[:30]
    row[11] = code
    row[12] = contractor.name[:40]
    row[13] = contractor.name[:255]
    row[14] = city
    row[15] = postal
    row[16] = street
    row[17] = contractor.nip[:20]
    row[18] = "Zakup" if kind in PURCHASE_TYPES else "Sprzedaż"
    row[21] = _epp_date(invoice.issue_date)
    row[22] = _epp_date(invoice.delivery_date or invoice.issue_date)
    row[23] = row[22]
    row[24] = str(len(invoice.lines))
    row[25] = "1"
    row[26] = "Detaliczna"
    row[27] = _epp_amount(invoice.net)
    row[28] = _epp_amount(invoice.vat)
    row[29] = _epp_amount(invoice.gross)
    row[30] = _epp_amount(invoice.net)
    row[32] = "0.0000"
    form, due, paid, payable = _payment_fields(invoice)
    row[33] = form
    row[34] = due
    row[35] = paid
    row[36] = payable
    row[37] = "0"
    row[38] = "0"
    row[39] = "1"
    row[40] = "0"
    row[44] = "0.0000"
    row[45] = "0.0000"
    row[46] = invoice.currency or "PLN"
    row[47] = "1.0000"
    row[52] = "0"
    row[53] = "0"
    row[54] = "0"
    row[56] = "0.0000"
    row[58] = "0.0000"
    row[59] = "Polska"
    row[60] = "PL"
    row[61] = "0"
    return row


def _line_row(line: LineItem, code: str) -> list[str]:
    net = _money(line.net_value)
    rate = _money(line.vat_rate)
    vat = (net * rate / Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    gross = net + vat
    unit_net = _money(line.unit_price)
    unit_gross = unit_net * (Decimal("1") + rate / Decimal("100"))
    quantity = _epp_amount(_plain(line.quantity) or "0")
    row = [""] * 22
    row[0] = line.number or "1"
    row[1] = "1"
    row[2] = code
    row[3] = "1"
    row[4] = "1"
    row[5] = "0"
    row[6] = "1"
    row[7] = "0.0000"
    row[8] = "0.0000"
    row[9] = (line.unit or "szt.")[:10]
    row[10] = quantity
    row[11] = quantity
    row[12] = "0.0000"
    row[13] = _epp_amount(line.unit_price)
    row[14] = _four(unit_gross)
    row[15] = _epp_amount(line.vat_rate)
    row[16] = _epp_amount(line.net_value)
    row[17] = _four(vat)
    row[18] = _four(gross)
    row[19] = _epp_amount(line.net_value)
    return row


def _catalog(contractors: dict[str, object], goods: dict[str, LineItem], endings: list[tuple[str, str]]) -> list[str]:
    contractor_rows = [_contractor_row(code, party) for code, party in contractors.items()]
    group_rows = [[code, "Podstawowa"] for code in contractors]
    extra_rows = [[code, "0", "1", "0", "0", "0", "0"] for code in contractors]
    goods_rows = [_goods_row(code, line) for code, line in goods.items()]
    price_rows = [_price_row(code, line) for code, line in goods.items()]
    goods_groups = [[code, "Podstawowa", ""] for code in goods]
    goods_extra = [[code, "0", "0", "0.0000", "0", "0", "0"] for code in goods]
    goods_cn = [[code, ""] for code in goods]
    goods_jpk = [[code, *["0"] * 13] for code in goods]
    done = [[label, stamp] for label, stamp in endings]
    markers = [[label, *["0"] * 30] for label, _stamp in endings]
    required = [[label, "0"] for label, _stamp in endings]
    return [
        _section("[NAGLOWEK]", [["KONTRAHENCI"]], {0}),
        _section("[ZAWARTOSC]", contractor_rows, CONTRACTOR_TEXT),
        _section("[NAGLOWEK]", [["GRUPYKONTRAHENTOW"]], {0}),
        _section("[ZAWARTOSC]", group_rows, {0, 1}),
        _section("[NAGLOWEK]", [["CECHYKONTRAHENTOW"]], {0}),
        _section("[ZAWARTOSC]", [], set()),
        _section("[NAGLOWEK]", [["DODATKOWEKONTRAHENTOW"]], {0}),
        _section("[ZAWARTOSC]", extra_rows, {0}),
        _section("[NAGLOWEK]", [["TOWARY"]], {0}),
        _section("[ZAWARTOSC]", goods_rows, GOODS_TEXT),
        _section("[NAGLOWEK]", [["CENNIK"]], {0}),
        _section("[ZAWARTOSC]", price_rows, {0, 1}),
        _section("[NAGLOWEK]", [["GRUPYTOWAROW"]], {0}),
        _section("[ZAWARTOSC]", goods_groups, {0, 1}),
        _section("[NAGLOWEK]", [["CECHYTOWAROW"]], {0}),
        _section("[ZAWARTOSC]", [], set()),
        _section("[NAGLOWEK]", [["DODATKOWETOWAROW"]], {0}),
        _section("[ZAWARTOSC]", goods_extra, {0}),
        _section("[NAGLOWEK]", [["TOWARYKODYCN"]], {0}),
        _section("[ZAWARTOSC]", goods_cn, {0}),
        _section("[NAGLOWEK]", [["TOWARYGRUPYJPKVAT"]], {0}),
        _section("[ZAWARTOSC]", goods_jpk, {0}),
        _section("[NAGLOWEK]", [["DATYZAKONCZENIA"]], {0}),
        _section("[ZAWARTOSC]", done, {0}),
        _section("[NAGLOWEK]", [["NUMERYIDENTYFIKACYJNENABYWCOW"]], {0}),
        _section("[ZAWARTOSC]", [], set()),
        _section("[NAGLOWEK]", [["PRZYCZYNYKOREKT"]], {0}),
        _section("[ZAWARTOSC]", [], set()),
        _section("[NAGLOWEK]", [["DOKUMENTYFISKALNEVAT"]], {0}),
        _section("[ZAWARTOSC]", [], set()),
        _section("[NAGLOWEK]", [["OPLATYDODATKOWE"]], {0}),
        _section("[ZAWARTOSC]", [], set()),
        _section("[NAGLOWEK]", [["WYMAGALNOSCMPP"]], {0}),
        _section("[ZAWARTOSC]", required, {0}),
        _section("[NAGLOWEK]", [["OPLATACUKROWA"]], {0}),
        _section("[ZAWARTOSC]", [], set()),
        _section("[NAGLOWEK]", [["DOKUMENTYZNACZNIKIJPKVAT"]], {0}),
        _section("[ZAWARTOSC]", markers, {0}),
        _section("[NAGLOWEK]", [["INFORMACJEWSTO"]], {0}),
        _section("[ZAWARTOSC]", [], set()),
        _section("[NAGLOWEK]", [["DATYUJECIAKOREKT"]], {0}),
        _section("[ZAWARTOSC]", [], set()),
    ]


def _contractor_row(code: str, party) -> list[str]:
    street, postal, city = _split_address(party.address)
    row = [""] * 30
    row[0] = "0"
    row[1] = code
    row[2] = party.name[:40]
    row[3] = party.name[:255]
    row[4] = city
    row[5] = postal
    row[6] = street
    row[7] = party.nip
    row[27] = "Polska"
    row[28] = "PL"
    row[29] = "0"
    return row


def _goods_row(code: str, line: LineItem) -> list[str]:
    rate = _plain(line.vat_rate) or "23"
    if "." in rate:
        rate = rate.split(".", 1)[0]
    name = (line.name or code)[:50]
    unit = (line.unit or "szt.")[:10]
    row = [""] * 42
    row[0] = "1"
    row[1] = code
    row[3] = line.gtin or code
    row[4] = name
    row[6] = name
    row[9] = unit
    row[10] = rate
    row[11] = _epp_amount(rate)
    row[12] = rate
    row[13] = _epp_amount(rate)
    row[14] = "0.0000"
    row[15] = "0.0000"
    row[17] = "0"
    row[21] = "0.0000"
    row[22] = "0"
    row[25] = "0"
    row[26] = unit
    row[27] = "0.0000"
    row[28] = "0.0000"
    row[30] = "0"
    row[32] = "0"
    row[33] = "0"
    return row


def _price_row(code: str, line: LineItem) -> list[str]:
    rate = _money(line.vat_rate)
    net = _money(line.unit_price)
    gross = net * (Decimal("1") + rate / Decimal("100"))
    return [code, "Detaliczna", _four(net), _four(gross), "0.0000", "0.0000", _four(net)]


def _party_code(party) -> str:
    return (_digits(party.nip) or party.name or "KONTRAHENT")[:20]


def _doc_number(number: str) -> str:
    digits = ""
    for character in number:
        if character.isdigit():
            digits += character
        elif digits:
            break
    return str(int(digits)) if digits else "1"


def _split_address(address: str) -> tuple[str, str, str]:
    parts = [
        part.strip()
        for part in address.split(",")
        if part.strip() and part.strip() not in {"PL", "Polska"}
    ]
    street = parts[0] if parts else ""
    postal = ""
    city = ""
    if len(parts) > 1:
        bits = parts[1].split(" ", 1)
        if bits and bits[0][:1].isdigit():
            postal = bits[0]
            city = bits[1] if len(bits) > 1 else ""
        else:
            city = parts[1]
    return street[:50], postal[:6], city[:30]


def _section(label: str, rows: list[list[str]], text_fields: set[int]) -> str:
    lines = [label]
    lines.extend(_format_row(row, text_fields) for row in rows)
    return "\r\n".join(lines) + "\r\n\r\n"


def _format_row(row: list[str], text_fields: set[int]) -> str:
    cells = []
    for index, value in enumerate(row):
        if index in text_fields and value:
            cells.append('"' + value.replace('"', '""') + '"')
        else:
            cells.append(value)
    return ",".join(cells)


def _document_identity(invoice: Invoice) -> tuple[str, str]:
    parts = invoice.number.split(" ", 1)
    if len(parts) == 2 and parts[0] in DOCUMENT_TYPES:
        return parts[0], parts[1]
    return "FS", invoice.number


def _goods_code(index: str, number: str) -> str:
    code = index.strip() or f"P{number or '0'}"
    return code[:20]


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


def _payment_fields(invoice: Invoice) -> tuple[str, str, str, str]:
    gross = _epp_amount(invoice.gross)
    form = (invoice.payment_form or "")[:30]
    if form == "przelew":
        return form, _epp_date(invoice.payment_due), "0.0000", gross
    if form == "gotówka":
        return form, "", gross, "0.0000"
    due = _epp_date(invoice.payment_due) if invoice.payment_due else ""
    return form, due, "0.0000", gross


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
