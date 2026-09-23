from pathlib import Path

import wx

from subksef.catalog.match import is_missing
from subksef.catalog.store import import_goods, list_goods, list_states, save_replacement
from subksef.invoice.epp import CatalogItem
from subksef.invoice.fa3 import Invoice, LineItem
from subksef.ui.office import CANVAS, TEXT, WHITE, face

REPLACED = frozenset({"auto", "reczna"})


class MissingFrame(wx.Frame):
    def __init__(self, parent: wx.Window, invoices: tuple[Invoice, ...], database: Path | None = None):
        super().__init__(parent, title="Niedodane", size=(760, 520))
        self.SetBackgroundColour(CANVAS)
        self._database = database
        self._invoices = invoices
        self._rows: tuple[tuple[int, int, LineItem], ...] = ()

        panel = wx.Panel(self)
        panel.SetBackgroundColour(WHITE)
        self._info = wx.StaticText(
            panel,
            label="Pozycje, których nie podmieniono na towar z bazy. Wpisz własny kod i nazwę.",
        )
        self._list = wx.ListBox(panel, style=wx.LB_SINGLE)
        self._list.SetBackgroundColour(WHITE)
        self._list.SetForegroundColour(TEXT)
        self._list.Bind(wx.EVT_LISTBOX, self._on_select)

        code_label = wx.StaticText(panel, label="Kod")
        self._code = wx.TextCtrl(panel)
        name_label = wx.StaticText(panel, label="Nazwa")
        self._name = wx.TextCtrl(panel)
        self._add = wx.Button(panel, label="Dodaj")
        self._add.SetFont(face(9, bold=True))
        self._add.Bind(wx.EVT_BUTTON, self._on_add)
        close = wx.Button(panel, label="Zamknij")
        close.Bind(wx.EVT_BUTTON, lambda _event: self.Close())

        form = wx.FlexGridSizer(2, 2, 8, 8)
        form.AddGrowableCol(1)
        form.Add(code_label, flag=wx.ALIGN_CENTER_VERTICAL)
        form.Add(self._code, flag=wx.EXPAND)
        form.Add(name_label, flag=wx.ALIGN_CENTER_VERTICAL)
        form.Add(self._name, flag=wx.EXPAND)

        buttons = wx.BoxSizer(wx.HORIZONTAL)
        buttons.Add(self._add, flag=wx.RIGHT, border=8)
        buttons.Add(close)

        root = wx.BoxSizer(wx.VERTICAL)
        root.Add(self._info, flag=wx.ALL, border=16)
        root.Add(self._list, proportion=1, flag=wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, border=16)
        root.Add(form, flag=wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, border=16)
        root.Add(buttons, flag=wx.ALIGN_CENTER | wx.BOTTOM, border=16)
        panel.SetSizer(root)
        self._reload()
        self.Centre()

    def _reload(self):
        self._code.ChangeValue("")
        self._name.ChangeValue("")
        try:
            goods = list_goods(path=self._database)
        except OSError:
            wx.MessageBox(
                "Nie udało się odczytać bazy towarów.",
                "Subksef",
                wx.OK | wx.ICON_WARNING,
            )
            goods = ()
        rows = []
        for document, invoice in enumerate(self._invoices):
            try:
                states = list_states(invoice.number, document, self._database)
            except OSError:
                states = {}
            for line_index, line in enumerate(invoice.lines):
                state = states.get(line_index)
                if state is not None and state[0] in REPLACED:
                    continue
                if not is_missing(line, goods):
                    continue
                rows.append((document, line_index, line))
        self._rows = tuple(rows)
        if self._rows:
            self._list.SetItems([_label(line) for _document, _index, line in self._rows])
            self._list.Enable()
            self._add.Enable()
            self._info.SetLabel("Pozycje, których nie podmieniono na towar z bazy. Wpisz własny kod i nazwę.")
            return
        self._list.SetItems(["Brak niedodanych pozycji na tej fakturze."])
        self._list.Enable(False)
        self._add.Enable(False)
        self._info.SetLabel("Brak niedodanych towarów.")

    def _on_select(self, _event):
        self._code.ChangeValue("")
        self._name.ChangeValue("")

    def _on_add(self, _event):
        selected = self._list.GetSelection()
        if selected == wx.NOT_FOUND or not self._rows:
            wx.MessageBox(
                "Wybierz pozycję z listy.",
                "Subksef",
                wx.OK | wx.ICON_INFORMATION,
            )
            return
        code = self._code.GetValue().strip()
        name = self._name.GetValue().strip()
        if not code or not name:
            wx.MessageBox(
                "Wpisz kod i nazwę.",
                "Subksef",
                wx.OK | wx.ICON_INFORMATION,
            )
            return
        document, line_index, line = self._rows[selected]
        invoice = self._invoices[document]
        item = CatalogItem(code=code[:20], name=name, net_price=line.unit_price, gross_price="")
        try:
            known = {entry.code.strip().casefold() for entry in list_goods(path=self._database)}
            if item.code.casefold() in known:
                wx.MessageBox(
                    "Taki kod jest już w bazie.",
                    "Subksef",
                    wx.OK | wx.ICON_INFORMATION,
                )
                return
            import_goods((item,), self._database)
            save_replacement(
                invoice.number,
                document,
                line_index,
                line.name,
                line.index,
                item,
                self._database,
                manual=True,
            )
        except OSError:
            wx.MessageBox(
                "Nie udało się zapisać towaru w bazie.",
                "Subksef",
                wx.OK | wx.ICON_WARNING,
            )
            return
        refresher = getattr(self.GetParent(), "refresh_goods", None)
        if refresher is not None:
            refresher()
        self._reload()


def _label(line: LineItem) -> str:
    code = line.index.strip() or "bez kodu"
    return f"niedodany    Lp {line.number or '—'}    {code}    {line.name}    {line.unit_price or '—'}"
