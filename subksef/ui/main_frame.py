import wx
from pathlib import Path

from subksef.conversion.convert import convert, output_paths, suggested_target
from subksef.invoice.epp import read_epp
from subksef.invoice.fa3 import Invoice, InvoiceReadError, read_invoice
from subksef.ui.edit_frame import EditFrame
from subksef.ui.goods_panel import GoodsPanel
from subksef.ui.missing_frame import MissingFrame
from subksef.ui.office import (
    CANVAS,
    CommandButton,
    Ribbon,
    RibbonGroup,
    card,
    face,
    field_label,
)
from subksef.ui.preview_frame import PreviewFrame

SOURCE_WILDCARD = (
    "Pliki faktur (*.xml;*.epp)|*.xml;*.epp|"
    "Pliki XML (*.xml)|*.xml|"
    "Pliki Subiekt (*.epp)|*.epp"
)


def _find_goods(window: wx.Window) -> GoodsPanel | None:
    if isinstance(window, GoodsPanel):
        return window
    for child in window.GetChildren():
        found = _find_goods(child)
        if found is not None:
            return found
    return None


class MainFrame(wx.Frame):
    def __init__(self):
        super().__init__(None, title="Subksef", size=(900, 560))
        self.SetBackgroundColour(CANVAS)
        self.CreateStatusBar()
        self.SetStatusText("Gotowe")

        panel = wx.Panel(self)
        panel.SetBackgroundColour(CANVAS)
        panel.SetFont(face())

        self._ribbon = Ribbon(panel)
        self._ribbon.on_select = self._show_page
        goods_shell, goods_body = card(panel)
        goods_body_sizer = wx.BoxSizer(wx.VERTICAL)
        self.goods = GoodsPanel(goods_body)
        goods_body_sizer.Add(self.goods, proportion=1, flag=wx.EXPAND)
        goods_body.SetSizer(goods_body_sizer)
        self._goods_card = goods_shell
        self.goods.selection_changed = self._on_goods_selection
        self._ribbon.add_page("Faktury", self._invoice_commands(self._ribbon, panel))
        self._ribbon.add_page("Towary", self._goods_commands(self._ribbon))

        root = wx.BoxSizer(wx.VERTICAL)
        root.Add(self._ribbon, flag=wx.EXPAND)
        root.Add(self._invoice_card, proportion=1, flag=wx.EXPAND | wx.ALL, border=16)
        root.Add(self._goods_card, proportion=1, flag=wx.EXPAND | wx.ALL, border=16)
        panel.SetSizer(root)
        frame = wx.BoxSizer(wx.VERTICAL)
        frame.Add(panel, proportion=1, flag=wx.EXPAND)
        self.SetSizer(frame)
        self._show_page("Faktury")
        self.Centre()

    def _invoice_commands(self, parent: wx.Window, host: wx.Window) -> wx.Panel:
        page = wx.Panel(parent)
        page.SetBackgroundColour(parent.GetBackgroundColour())
        source = RibbonGroup(page, "Plik źródłowy")
        source.add(CommandButton(source, "Wybierz plik", wx.ART_FILE_OPEN, self.on_choose_source))
        source.add(CommandButton(source, "Podgląd", wx.ART_FIND, self.on_preview))
        source.add(CommandButton(source, "Edycja", wx.ART_EDIT, self.on_edit))
        source.add(CommandButton(source, "Niedodane", wx.ART_LIST_VIEW, self.on_missing))
        convert = RibbonGroup(page, "Konwersja")
        convert.add(CommandButton(convert, "Konwertuj", wx.ART_GO_FORWARD, self.on_convert))
        row = wx.BoxSizer(wx.HORIZONTAL)
        row.Add(source, flag=wx.EXPAND | wx.RIGHT, border=8)
        row.Add(convert, flag=wx.EXPAND)
        page.SetSizer(row)

        shell, card_body = card(host)
        self._invoice_card = shell
        self.source_path = wx.TextCtrl(card_body)
        source_button = wx.Button(card_body, label="Wybierz")
        source_button.Bind(wx.EVT_BUTTON, self.on_choose_source)
        self.output_path = wx.TextCtrl(card_body)
        output_button = wx.Button(card_body, label="Wybierz")
        output_button.Bind(wx.EVT_BUTTON, self.on_choose_output)
        source_row = wx.BoxSizer(wx.HORIZONTAL)
        source_row.Add(self.source_path, proportion=1, flag=wx.EXPAND | wx.RIGHT, border=8)
        source_row.Add(source_button, flag=wx.ALIGN_CENTER_VERTICAL)
        output_row = wx.BoxSizer(wx.HORIZONTAL)
        output_row.Add(self.output_path, proportion=1, flag=wx.EXPAND | wx.RIGHT, border=8)
        output_row.Add(output_button, flag=wx.ALIGN_CENTER_VERTICAL)
        body = wx.BoxSizer(wx.VERTICAL)
        body.Add(field_label(card_body, "Plik źródłowy"), flag=wx.ALL, border=16)
        body.Add(source_row, flag=wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, border=16)
        body.Add(field_label(card_body, "Tu powstanie przerobiony plik"), flag=wx.LEFT | wx.RIGHT | wx.BOTTOM, border=16)
        body.Add(output_row, flag=wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, border=16)
        card_body.SetSizer(body)
        return page

    def _goods_commands(self, parent: wx.Window) -> wx.Panel:
        page = wx.Panel(parent)
        page.SetBackgroundColour(parent.GetBackgroundColour())
        incoming = RibbonGroup(page, "Import")
        incoming.add(CommandButton(incoming, "Wybierz EPP", wx.ART_FILE_OPEN, self.goods.on_choose))
        incoming.add(CommandButton(incoming, "Wczytaj", wx.ART_GO_DOWN, self.goods.on_load))
        goods = RibbonGroup(page, "Towary")
        self._remove_goods = CommandButton(goods, "Usuń", wx.ART_DELETE, self.goods.on_remove)
        self._remove_goods.Enable(False)
        goods.add(self._remove_goods)
        row = wx.BoxSizer(wx.HORIZONTAL)
        row.Add(incoming, flag=wx.EXPAND | wx.RIGHT, border=8)
        row.Add(goods, flag=wx.EXPAND)
        page.SetSizer(row)
        return page

    def _show_page(self, name: str):
        invoice = name == "Faktury"
        self._invoice_card.Show(invoice)
        self._goods_card.Show(not invoice)
        self.Layout()

    def _on_goods_selection(self, selected: bool):
        self._remove_goods.Enable(selected)

    def on_choose_source(self, _event):
        with wx.FileDialog(
            self,
            "Wybierz plik",
            wildcard=SOURCE_WILDCARD,
            style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST,
        ) as dialog:
            if dialog.ShowModal() == wx.ID_CANCEL:
                return
            path = dialog.GetPath()

        self.source_path.SetValue(path)
        self.output_path.SetValue(str(suggested_target(Path(path))))
        self.SetStatusText(f"Wybrano plik: {Path(path).name}")

    def on_preview(self, _event):
        invoices = self._read_invoices()
        if invoices is None:
            return
        preview = PreviewFrame(self, invoices[0] if len(invoices) == 1 else invoices)
        preview.Show()

    def on_edit(self, _event):
        invoices = self._read_invoices()
        if invoices is None:
            return
        editor = EditFrame(self, invoices)
        editor.Show()

    def on_missing(self, _event):
        invoices = self._read_invoices()
        if invoices is None:
            return
        missing = MissingFrame(self, invoices)
        missing.Show()

    def refresh_goods(self):
        for child in self.GetChildren():
            found = _find_goods(child)
            if found is not None:
                found.refresh()
                return

    def _read_invoices(self) -> tuple[Invoice, ...] | None:
        path = self.source_path.GetValue().strip()
        if not path:
            wx.MessageBox(
                "Najpierw wybierz plik XML albo EPP.",
                "Subksef",
                wx.OK | wx.ICON_INFORMATION,
            )
            return None
        if not Path(path).is_file():
            wx.MessageBox(
                "Nie znaleziono pliku.",
                "Subksef",
                wx.OK | wx.ICON_WARNING,
            )
            return None
        suffix = Path(path).suffix.lower()
        try:
            if suffix == ".xml":
                return (read_invoice(path),)
            if suffix == ".epp":
                return read_epp(path)
        except InvoiceReadError as error:
            wx.MessageBox(str(error), "Subksef", wx.OK | wx.ICON_WARNING)
            return None
        wx.MessageBox(
            "Podgląd obsługuje pliki XML i EPP.",
            "Subksef",
            wx.OK | wx.ICON_INFORMATION,
        )
        return None

    def on_choose_output(self, _event):
        source = Path(self.source_path.GetValue().strip())
        current = self.output_path.GetValue().strip()
        output = Path(current) if current else suggested_target(source)
        wildcard = "Wszystkie pliki (*.*)|*.*"
        if source.suffix.lower() == ".xml":
            wildcard = "Pliki Subiekt (*.epp)|*.epp"
        elif source.suffix.lower() == ".epp":
            wildcard = "Pliki XML (*.xml)|*.xml"

        with wx.FileDialog(
            self,
            "Gdzie zapisać przerobiony plik",
            defaultDir=str(output.parent),
            defaultFile=output.name,
            wildcard=wildcard,
            style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT,
        ) as dialog:
            if dialog.ShowModal() == wx.ID_CANCEL:
                return
            self.output_path.SetValue(dialog.GetPath())

    def on_convert(self, _event):
        source_text = self.source_path.GetValue().strip()
        if not source_text:
            wx.MessageBox(
                "Najpierw wybierz plik XML albo EPP.",
                "Subksef",
                wx.OK | wx.ICON_INFORMATION,
            )
            return
        source = Path(source_text)
        if not source.is_file():
            wx.MessageBox(
                "Nie znaleziono pliku.",
                "Subksef",
                wx.OK | wx.ICON_WARNING,
            )
            return
        output_text = self.output_path.GetValue().strip()
        target = Path(output_text) if output_text else suggested_target(source)
        try:
            destinations = output_paths(source, target)
        except InvoiceReadError as error:
            wx.MessageBox(str(error), "Subksef", wx.OK | wx.ICON_WARNING)
            return
        existing = [path for path in destinations if path.exists()]
        if existing:
            answer = wx.MessageBox(
                "Plik wynikowy już istnieje. Zastąpić go?",
                "Subksef",
                wx.YES_NO | wx.ICON_QUESTION,
            )
            if answer != wx.YES:
                return
        try:
            written = convert(source, target)
        except InvoiceReadError as error:
            wx.MessageBox(str(error), "Subksef", wx.OK | wx.ICON_WARNING)
            return
        except OSError:
            wx.MessageBox(
                "Nie udało się zapisać pliku.",
                "Subksef",
                wx.OK | wx.ICON_WARNING,
            )
            return
        self.output_path.SetValue(str(written[0]))
        self.SetStatusText("Konwersja zakończona")
        wx.MessageBox(
            "Zapisano:\n" + "\n".join(str(path) for path in written),
            "Subksef",
            wx.OK | wx.ICON_INFORMATION,
        )
