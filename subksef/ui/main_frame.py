import wx
from pathlib import Path

from subksef.conversion.convert import convert, output_paths, suggested_target
from subksef.invoice.epp import read_epp
from subksef.invoice.fa3 import Invoice, InvoiceReadError, read_invoice
from subksef.ui.edit_frame import EditFrame
from subksef.ui.goods_panel import GoodsPanel
from subksef.ui.missing_frame import MissingFrame
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
        self.SetBackgroundColour(wx.WHITE)

        panel = wx.Panel(self)
        panel.SetBackgroundColour(wx.WHITE)

        title = wx.StaticText(panel, label="Subksef")
        title_font = title.GetFont()
        title_font.SetPointSize(22)
        title_font.SetWeight(wx.FONTWEIGHT_BOLD)
        title.SetFont(title_font)

        notebook = wx.Notebook(panel)
        invoice_page = wx.Panel(notebook)
        invoice_page.SetBackgroundColour(wx.WHITE)
        notebook.AddPage(invoice_page, "Faktury")
        notebook.AddPage(GoodsPanel(notebook), "Towary")

        source_label = wx.StaticText(invoice_page, label="Plik źródłowy")
        self.source_path = wx.TextCtrl(invoice_page)
        source_button = wx.Button(invoice_page, label="Wybierz")
        source_button.Bind(wx.EVT_BUTTON, self.on_choose_source)
        preview_button = wx.Button(invoice_page, label="Podgląd")
        preview_button.Bind(wx.EVT_BUTTON, self.on_preview)
        edit_button = wx.Button(invoice_page, label="Edycja")
        edit_button.Bind(wx.EVT_BUTTON, self.on_edit)
        missing_button = wx.Button(invoice_page, label="Niedodane")
        missing_button.Bind(wx.EVT_BUTTON, self.on_missing)

        output_label = wx.StaticText(
            invoice_page,
            label="Tu powstanie przerobiony plik",
        )
        self.output_path = wx.TextCtrl(invoice_page)
        output_button = wx.Button(invoice_page, label="Wybierz")
        output_button.Bind(wx.EVT_BUTTON, self.on_choose_output)

        convert_button = wx.Button(invoice_page, label="Konwertuj")
        convert_button.Bind(wx.EVT_BUTTON, self.on_convert)

        source_row = wx.BoxSizer(wx.HORIZONTAL)
        source_row.Add(self.source_path, proportion=1, flag=wx.EXPAND | wx.RIGHT, border=8)
        source_row.Add(source_button, flag=wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, border=8)
        source_row.Add(preview_button, flag=wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, border=8)
        source_row.Add(edit_button, flag=wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, border=8)
        source_row.Add(missing_button, flag=wx.ALIGN_CENTER_VERTICAL)

        output_row = wx.BoxSizer(wx.HORIZONTAL)
        output_row.Add(self.output_path, proportion=1, flag=wx.EXPAND | wx.RIGHT, border=8)
        output_row.Add(output_button, flag=wx.ALIGN_CENTER_VERTICAL)

        invoice = wx.BoxSizer(wx.VERTICAL)
        invoice.Add(source_label, flag=wx.LEFT | wx.RIGHT | wx.TOP | wx.BOTTOM, border=16)
        invoice.Add(source_row, flag=wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, border=16)
        invoice.Add(output_label, flag=wx.LEFT | wx.RIGHT | wx.BOTTOM, border=16)
        invoice.Add(output_row, flag=wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, border=16)
        invoice.Add(convert_button, flag=wx.ALIGN_CENTER | wx.TOP | wx.BOTTOM, border=8)
        invoice_page.SetSizer(invoice)

        root = wx.BoxSizer(wx.VERTICAL)
        root.Add(title, flag=wx.ALIGN_CENTER | wx.TOP | wx.BOTTOM, border=16)
        root.Add(notebook, proportion=1, flag=wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, border=12)

        panel.SetSizer(root)
        self.Centre()

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
        wx.MessageBox(
            "Zapisano:\n" + "\n".join(str(path) for path in written),
            "Subksef",
            wx.OK | wx.ICON_INFORMATION,
        )
