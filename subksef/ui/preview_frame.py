import wx

from subksef.invoice.fa3 import Invoice, Party

LINE_COLUMNS = (
    ("Lp", 50),
    ("Nazwa", 280),
    ("Indeks", 90),
    ("GTIN", 140),
    ("Jm", 50),
    ("Ilość", 70),
    ("Cena netto", 100),
    ("Wartość netto", 120),
    ("VAT %", 70),
)


class PreviewFrame(wx.Frame):
    def __init__(self, parent: wx.Window, invoice: Invoice | tuple[Invoice, ...]):
        self._invoices = invoice if isinstance(invoice, tuple) else (invoice,)
        self._index = 0
        super().__init__(parent, title="Podgląd", size=(1000, 720))
        self.SetBackgroundColour(wx.WHITE)

        panel = wx.Panel(self)
        panel.SetBackgroundColour(wx.WHITE)

        self._title = wx.StaticText(panel, label="")
        title_font = self._title.GetFont()
        title_font.SetPointSize(16)
        title_font.SetWeight(wx.FONTWEIGHT_BOLD)
        self._title.SetFont(title_font)

        self._dates = wx.StaticText(panel, label="")
        self._seller = _PartyBox(panel, "Sprzedawca")
        self._buyer = _PartyBox(panel, "Nabywca")
        self._summary = wx.StaticText(panel, label="")

        self._lines = wx.ListCtrl(panel, style=wx.LC_REPORT | wx.LC_SINGLE_SEL)
        for index, (label, width) in enumerate(LINE_COLUMNS):
            self._lines.InsertColumn(index, label, width=width)

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
        root.Add(self._dates, flag=wx.ALIGN_CENTER | wx.TOP | wx.BOTTOM, border=8)
        root.Add(parties, flag=wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, border=16)
        root.Add(self._summary, flag=wx.ALIGN_CENTER | wx.LEFT | wx.RIGHT | wx.BOTTOM, border=16)
        root.Add(self._lines, proportion=1, flag=wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, border=16)
        if len(self._invoices) > 1:
            root.Add(navigation, flag=wx.ALIGN_CENTER | wx.BOTTOM, border=8)
        root.Add(close_button, flag=wx.ALIGN_CENTER | wx.BOTTOM, border=16)

        panel.SetSizer(root)
        self._show_current()
        self.Centre()

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
        self.SetTitle(f"Podgląd {invoice.number}")
        self._title.SetLabel(invoice.number or "Faktura")
        self._dates.SetLabel(
            f"Wystawienie: {invoice.issue_date or '—'}    "
            f"Dostawa: {invoice.delivery_date or '—'}    "
            f"Termin płatności: {invoice.payment_due or '—'}"
        )
        self._seller.set_party(invoice.seller)
        self._buyer.set_party(invoice.buyer)
        self._summary.SetLabel(
            f"Netto: {invoice.net or '—'}    "
            f"VAT: {invoice.vat or '—'}    "
            f"Brutto: {invoice.gross or '—'}    "
            f"Waluta: {invoice.currency or '—'}    "
            f"Płatność: {invoice.payment_form or '—'}"
        )
        self._lines.DeleteAllItems()
        for row, item in enumerate(invoice.lines):
            self._lines.InsertItem(row, item.number)
            self._lines.SetItem(row, 1, item.name)
            self._lines.SetItem(row, 2, item.index)
            self._lines.SetItem(row, 3, item.gtin)
            self._lines.SetItem(row, 4, item.unit)
            self._lines.SetItem(row, 5, item.quantity)
            self._lines.SetItem(row, 6, item.unit_price)
            self._lines.SetItem(row, 7, item.net_value)
            self._lines.SetItem(row, 8, item.vat_rate)
        if len(self._invoices) > 1:
            self._position.SetLabel(f"Dokument {self._index + 1} z {len(self._invoices)}")
            self._previous.Enable(self._index > 0)
            self._next.Enable(self._index < len(self._invoices) - 1)
        self.Layout()


class _PartyBox:
    def __init__(self, parent: wx.Window, heading: str):
        self.sizer = wx.BoxSizer(wx.VERTICAL)
        title = wx.StaticText(parent, label=heading)
        title_font = title.GetFont()
        title_font.SetWeight(wx.FONTWEIGHT_BOLD)
        title.SetFont(title_font)
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
