import wx

from subksef.invoice.fa3 import Invoice, Party, payment_label
from subksef.ui.office import CANVAS, MUTED, NAVY, TEXT, WHITE, face, fit_on_screen

LINE_COLUMNS = (
    ("Lp", 50),
    ("Nazwa", 280),
    ("Indeks", 90),
    ("GTIN", 140),
    ("Jm", 50),
    ("Ilość", 70),
    ("Cena netto", 100),
    ("Cena po rabacie", 120),
    ("Kwota rabatu", 110),
    ("Wartość netto", 120),
    ("VAT %", 70),
)


class PreviewFrame(wx.Frame):
    def __init__(self, parent: wx.Window, invoice: Invoice | tuple[Invoice, ...]):
        self._invoices = invoice if isinstance(invoice, tuple) else (invoice,)
        self._index = 0
        super().__init__(parent, title="Podgląd", size=(1000, 720))
        self.SetBackgroundColour(CANVAS)

        panel = wx.Panel(self)
        panel.SetBackgroundColour(WHITE)

        self._title = wx.StaticText(panel, label="")
        self._title.SetFont(face(16, bold=True))
        self._title.SetForegroundColour(TEXT)

        self._dates = wx.StaticText(panel, label="")
        self._dates.SetForegroundColour(MUTED)
        self._payment = wx.StaticText(panel, label="")
        self._payment.SetFont(face(10, bold=True))
        self._payment.SetForegroundColour(TEXT)
        self._seller = _PartyBox(panel, "Sprzedawca")
        self._buyer = _PartyBox(panel, "Nabywca")
        self._summary = wx.StaticText(panel, label="")

        self._scroll = wx.ScrolledWindow(panel, style=wx.VSCROLL | wx.HSCROLL)
        self._scroll.SetScrollRate(16, 16)
        self._scroll.SetBackgroundColour(WHITE)
        self._lines = wx.BoxSizer(wx.VERTICAL)
        self._scroll.SetSizer(self._lines)

        self._previous = wx.Button(panel, label="Poprzedni")
        self._position = wx.StaticText(panel, label="")
        self._next = wx.Button(panel, label="Następny")
        self._previous.Bind(wx.EVT_BUTTON, self._show_previous)
        self._next.Bind(wx.EVT_BUTTON, self._show_next)
        navigation = wx.BoxSizer(wx.HORIZONTAL)
        navigation.Add(self._previous, flag=wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, border=12)
        navigation.Add(self._position, flag=wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, border=12)
        navigation.Add(self._next, flag=wx.ALIGN_CENTER_VERTICAL)

        close_button = wx.Button(panel, label="Zamknij")
        close_button.Bind(wx.EVT_BUTTON, lambda _event: self.Close())

        parties = wx.BoxSizer(wx.HORIZONTAL)
        parties.Add(self._seller.sizer, proportion=1, flag=wx.EXPAND | wx.RIGHT, border=16)
        parties.Add(self._buyer.sizer, proportion=1, flag=wx.EXPAND)

        root = wx.BoxSizer(wx.VERTICAL)
        root.Add(self._title, flag=wx.ALIGN_CENTER | wx.TOP, border=16)
        root.Add(self._dates, flag=wx.ALIGN_CENTER | wx.TOP, border=8)
        root.Add(self._payment, flag=wx.ALIGN_CENTER | wx.TOP | wx.BOTTOM, border=8)
        root.Add(parties, flag=wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, border=16)
        root.Add(self._summary, flag=wx.ALIGN_CENTER | wx.LEFT | wx.RIGHT | wx.BOTTOM, border=16)
        root.Add(self._scroll, proportion=1, flag=wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, border=16)
        if len(self._invoices) > 1:
            root.Add(navigation, flag=wx.ALIGN_CENTER | wx.BOTTOM, border=8)
        root.Add(close_button, flag=wx.ALIGN_CENTER | wx.BOTTOM, border=16)

        panel.SetSizer(root)
        self._show_current()
        fit_on_screen(self)

    def _show_previous(self, _event):
        if self._index > 0:
            self._index -= 1
            self._show_current()

    def _show_next(self, _event):
        if self._index < len(self._invoices) - 1:
            self._index += 1
            self._show_current()

    def _show_current(self):
        invoice = self._invoices[self._index]
        self.SetTitle(f"Podgląd — {invoice.number or 'Faktura'}")
        self._title.SetLabel(invoice.number or "Faktura")
        self._dates.SetLabel(
            f"Wystawienie: {invoice.issue_date or '—'}    "
            f"Dostawa: {invoice.delivery_date or '—'}"
        )
        self._payment.SetLabel(payment_label(invoice))
        self._seller.set_party(invoice.seller)
        self._buyer.set_party(invoice.buyer)
        self._summary.SetLabel(
            f"Netto: {invoice.net or '—'}    "
            f"VAT: {invoice.vat or '—'}    "
            f"Brutto: {invoice.gross or '—'}    "
            f"Waluta: {invoice.currency or '—'}"
        )
        self._lines.Clear(delete_windows=True)
        self._lines.Add(_table_row(self._scroll, [label for label, _width in LINE_COLUMNS], header=True), flag=wx.BOTTOM, border=6)
        for item in invoice.lines:
            self._lines.Add(
                _table_row(
                    self._scroll,
                    [
                        item.number,
                        item.name,
                        item.index,
                        item.gtin,
                        item.unit,
                        item.quantity,
                        item.unit_price,
                        item.price_after_discount or item.unit_price,
                        item.discount_amount or "0,00",
                        item.net_value,
                        item.vat_rate,
                    ],
                ),
                flag=wx.BOTTOM,
                border=2,
            )
        self._scroll.FitInside()
        if len(self._invoices) > 1:
            self._position.SetLabel(f"Dokument {self._index + 1} z {len(self._invoices)}")
            self._previous.Enable(self._index > 0)
            self._next.Enable(self._index < len(self._invoices) - 1)
        self.Layout()


AFTER_COLUMN = 7


def _table_row(parent: wx.Window, values: list[str], header: bool = False) -> wx.Panel:
    row = wx.Panel(parent)
    row.SetBackgroundColour(WHITE)
    sizer = wx.BoxSizer(wx.HORIZONTAL)
    for index, ((_title, width), value) in enumerate(zip(LINE_COLUMNS, values)):
        highlight = index == AFTER_COLUMN
        text = wx.StaticText(row, label=value or "—", size=(width, -1), style=wx.ST_ELLIPSIZE_END)
        if header or highlight:
            text.SetFont(face(9, bold=True))
        text.SetForegroundColour(NAVY if highlight else TEXT)
        sizer.Add(text, flag=wx.RIGHT, border=8)
    row.SetSizer(sizer)
    return row


class _PartyBox:
    def __init__(self, parent: wx.Window, heading: str):
        self.sizer = wx.BoxSizer(wx.VERTICAL)
        title = wx.StaticText(parent, label=heading)
        title.SetFont(face(10, bold=True))
        title.SetForegroundColour(TEXT)
        self._name = wx.StaticText(parent, label="")
        self._nip = wx.StaticText(parent, label="")
        self._address = wx.StaticText(parent, label="")
        self.sizer.Add(title, flag=wx.BOTTOM, border=4)
        self.sizer.Add(self._name)
        self.sizer.Add(self._nip, flag=wx.TOP, border=2)
        self.sizer.Add(self._address, flag=wx.TOP, border=2)

    def set_party(self, party: Party):
        self._name.SetLabel(party.name or "—")
        self._nip.SetLabel(f"NIP: {party.nip or '—'}")
        self._address.SetLabel(party.address or "—")
