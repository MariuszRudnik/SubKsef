import wx
from pathlib import Path

from subksef.catalog.store import delete_good, import_goods, list_goods
from subksef.invoice.epp import read_catalog
from subksef.invoice.fa3 import InvoiceReadError
from subksef.ui.office import WHITE, field_label

COLUMNS = (
    ("Kod", 140),
    ("Nazwa", 360),
    ("Cena netto", 120),
    ("Cena brutto", 120),
)


class GoodsPanel(wx.Panel):
    def __init__(self, parent: wx.Window):
        super().__init__(parent)
        self.SetBackgroundColour(WHITE)
        self.selection_changed = None

        self.path = wx.TextCtrl(self)
        choose = wx.Button(self, label="Wybierz")
        choose.Bind(wx.EVT_BUTTON, self.on_choose)
        load = wx.Button(self, label="Wczytaj")
        load.Bind(wx.EVT_BUTTON, self.on_load)

        path_row = wx.BoxSizer(wx.HORIZONTAL)
        path_row.Add(self.path, proportion=1, flag=wx.EXPAND | wx.RIGHT, border=8)
        path_row.Add(choose, flag=wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, border=8)
        path_row.Add(load, flag=wx.ALIGN_CENTER_VERTICAL)

        self.status = wx.StaticText(self, label="")
        self.search = wx.TextCtrl(self)
        self.search.Bind(wx.EVT_TEXT, self.on_search)

        self.table = wx.ListCtrl(self, style=wx.LC_REPORT | wx.LC_SINGLE_SEL)
        self.table.SetBackgroundColour(WHITE)
        for index, (title, width) in enumerate(COLUMNS):
            self.table.InsertColumn(index, title, width=width)
        self.table.Bind(wx.EVT_LIST_ITEM_SELECTED, self._on_selection)
        self.table.Bind(wx.EVT_LIST_ITEM_DESELECTED, self._on_selection)
        self._remove = wx.Button(self, label="Usuń")
        self._remove.Bind(wx.EVT_BUTTON, self.on_remove)
        self._remove.Enable(False)

        root = wx.BoxSizer(wx.VERTICAL)
        root.Add(field_label(self, "Plik EPP z towarami i usługami"), flag=wx.ALL, border=16)
        root.Add(path_row, flag=wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, border=16)
        root.Add(self.status, flag=wx.LEFT | wx.RIGHT | wx.BOTTOM, border=16)
        root.Add(field_label(self, "Szukaj"), flag=wx.LEFT | wx.RIGHT | wx.BOTTOM, border=8)
        root.Add(self.search, flag=wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, border=16)
        root.Add(self.table, proportion=1, flag=wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, border=16)
        root.Add(self._remove, flag=wx.ALIGN_LEFT | wx.LEFT | wx.BOTTOM, border=16)
        self.SetSizer(root)
        self.refresh()

    def _on_selection(self, event):
        selected = self.table.GetFirstSelected() != -1
        self._remove.Enable(selected)
        if self.selection_changed is not None:
            self.selection_changed(selected)
        event.Skip()

    def on_choose(self, _event):
        with wx.FileDialog(
            self,
            "Wybierz plik EPP z towarami",
            wildcard="Pliki Subiekt (*.epp)|*.epp",
            style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST,
        ) as dialog:
            if dialog.ShowModal() == wx.ID_CANCEL:
                return
            self.path.SetValue(dialog.GetPath())

    def on_load(self, _event):
        path = self.path.GetValue().strip()
        if not path:
            wx.MessageBox(
                "Najpierw wybierz plik EPP z towarami.",
                "Subksef",
                wx.OK | wx.ICON_INFORMATION,
            )
            return
        if not Path(path).is_file():
            wx.MessageBox(
                "Nie znaleziono pliku.",
                "Subksef",
                wx.OK | wx.ICON_WARNING,
            )
            return
        try:
            items = read_catalog(path)
            added, skipped = import_goods(items)
        except InvoiceReadError as error:
            wx.MessageBox(str(error), "Subksef", wx.OK | wx.ICON_WARNING)
            return
        except OSError:
            wx.MessageBox(
                "Nie udało się zapisać bazy towarów.",
                "Subksef",
                wx.OK | wx.ICON_WARNING,
            )
            return
        self.refresh()
        self.status.SetLabel(f"Dodano {added}, pominięto {skipped}.")

    def on_search(self, _event):
        self.refresh()

    def on_remove(self, _event):
        row = self.table.GetFirstSelected()
        if row == -1:
            wx.MessageBox(
                "Najpierw zaznacz towar na liście.",
                "Subksef",
                wx.OK | wx.ICON_INFORMATION,
            )
            return
        code = self.table.GetItemText(row, 0)
        name = self.table.GetItemText(row, 1)
        answer = wx.MessageBox(
            f"Czy na pewno usunąć ten produkt z bazy danych?\n{code}  {name}",
            "Subksef",
            wx.YES_NO | wx.ICON_QUESTION,
        )
        if answer != wx.YES:
            return
        try:
            delete_good(code)
        except OSError:
            wx.MessageBox(
                "Nie udało się usunąć towaru z bazy.",
                "Subksef",
                wx.OK | wx.ICON_WARNING,
            )
            return
        self.refresh()
        self.status.SetLabel(f"Usunięto {code}.")

    def refresh(self):
        self.table.DeleteAllItems()
        self._remove.Enable(False)
        if self.selection_changed is not None:
            self.selection_changed(False)
        try:
            items = list_goods(self.search.GetValue())
        except OSError:
            wx.MessageBox(
                "Nie udało się odczytać bazy towarów.",
                "Subksef",
                wx.OK | wx.ICON_WARNING,
            )
            return
        for item in items:
            row = self.table.InsertItem(self.table.GetItemCount(), item.code)
            self.table.SetItem(row, 1, item.name)
            self.table.SetItem(row, 2, item.net_price)
            self.table.SetItem(row, 3, item.gross_price)
