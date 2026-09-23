from pathlib import Path

import wx

from subksef.catalog.match import suggest_good
from subksef.catalog.store import list_goods, list_states, save_replacement, skip_replacement
from subksef.invoice.epp import CatalogItem
from subksef.invoice.fa3 import Invoice, Party

RED = wx.Colour(198, 40, 40)
YELLOW = wx.Colour(196, 145, 0)
GREEN = wx.Colour(46, 125, 50)
MATCH_LIMIT = 8


def _rank(item: CatalogItem, query: str) -> int:
    folded = query.casefold()
    code = item.code.casefold()
    name = item.name.casefold()
    if code == folded:
        return 0
    if name == folded:
        return 1
    if code.startswith(folded):
        return 2
    if name.startswith(folded):
        return 3
    return 4


class EditFrame(wx.Frame):
    def __init__(
        self,
        parent: wx.Window,
        invoices: tuple[Invoice, ...],
        database: Path | None = None,
    ):
        self._invoices = invoices
        self._database = database
        self._index = 0
        super().__init__(parent, title="Edycja", size=(1100, 760))
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
        hint = wx.StaticText(
            panel,
            label="Czerwona zostaje z faktury. Żółta jest dopasowana po nazwie i cenie. Zielona jest wybrana ręcznie.",
        )

        self._scroll = wx.ScrolledWindow(panel, style=wx.VSCROLL)
        self._scroll.SetScrollRate(0, 16)
        self._scroll.SetBackgroundColour(wx.WHITE)
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
        root.Add(self._dates, flag=wx.ALIGN_CENTER | wx.TOP | wx.BOTTOM, border=8)
        root.Add(parties, flag=wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, border=16)
        root.Add(self._summary, flag=wx.ALIGN_CENTER | wx.LEFT | wx.RIGHT | wx.BOTTOM, border=8)
        root.Add(hint, flag=wx.ALIGN_CENTER | wx.LEFT | wx.RIGHT | wx.BOTTOM, border=12)
        root.Add(self._scroll, proportion=1, flag=wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, border=16)
        if len(self._invoices) > 1:
            root.Add(navigation, flag=wx.ALIGN_CENTER | wx.BOTTOM, border=8)
        root.Add(close_button, flag=wx.ALIGN_CENTER | wx.BOTTOM, border=16)

        panel.SetSizer(root)
        self._suggest = _SuggestList(self)
        self._scroll.Bind(wx.EVT_SCROLLWIN, self._follow_suggest)
        self.Bind(wx.EVT_MOVE, self._follow_suggest)
        self._show_current()
        self.Centre()

    def _follow_suggest(self, event):
        self._suggest.follow()
        event.Skip()

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
        self.SetTitle(f"Edycja {invoice.number}")
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
        self._suggest.Hide()
        self._lines.Clear(delete_windows=True)
        self._lines.Add(_list_header(self._scroll), flag=wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, border=4)
        try:
            stored = list_states(invoice.number, self._index, self._database)
            goods = list_goods(path=self._database)
        except OSError:
            wx.MessageBox(
                "Nie udało się odczytać podmian tej faktury.",
                "Subksef",
                wx.OK | wx.ICON_WARNING,
            )
            stored = {}
            goods = ()
        for line_index, line in enumerate(invoice.lines):
            state = stored.get(line_index)
            if state is None:
                match = suggest_good(line, goods)
                if match is not None and self._assign(line_index, match, manual=False):
                    state = ("auto", match)
            item = None
            manual = False
            if state is not None and state[0] != "pominieta":
                item = state[1]
                manual = state[0] == "reczna"
            row = _LineRow(self._scroll, line_index, line, item, manual, self._assign, self._clear)
            self._lines.Add(row, flag=wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, border=2)
        if len(self._invoices) > 1:
            self._position.SetLabel(f"Dokument {self._index + 1} z {len(self._invoices)}")
            self._previous.Enable(self._index > 0)
            self._next.Enable(self._index < len(self._invoices) - 1)
        self._scroll.FitInside()
        self._scroll.Scroll(0, 0)
        self.Layout()

    def _assign(self, line_index: int, item: CatalogItem, manual: bool = True) -> bool:
        invoice = self._invoices[self._index]
        line = invoice.lines[line_index]
        try:
            save_replacement(
                invoice.number,
                self._index,
                line_index,
                line.name,
                line.index,
                item,
                self._database,
                manual=manual,
            )
        except OSError:
            wx.MessageBox(
                "Nie udało się zapisać podmiany.",
                "Subksef",
                wx.OK | wx.ICON_WARNING,
            )
            return False
        return True

    def _clear(self, line_index: int) -> bool:
        invoice = self._invoices[self._index]
        line = invoice.lines[line_index]
        try:
            skip_replacement(
                invoice.number,
                self._index,
                line_index,
                line.name,
                line.index,
                self._database,
            )
        except OSError:
            wx.MessageBox(
                "Nie udało się usunąć podmiany.",
                "Subksef",
                wx.OK | wx.ICON_WARNING,
            )
            return False
        return True

    def _relayout(self):
        self._scroll.FitInside()
        self._scroll.Layout()


def _column(parent: wx.Window, label: str, width: int, bold: bool = False) -> wx.StaticText:
    text = wx.StaticText(parent, label=label, size=(width, -1), style=wx.ST_ELLIPSIZE_END)
    if bold:
        font = text.GetFont()
        font.SetWeight(wx.FONTWEIGHT_BOLD)
        text.SetFont(font)
    return text


def _list_header(parent: wx.Window) -> wx.Panel:
    header = wx.Panel(parent)
    header.SetBackgroundColour(wx.WHITE)
    number = _column(header, "Lp", 36, bold=True)
    name = _column(header, "Nazwa", 280, bold=True)
    index = _column(header, "Indeks", 90, bold=True)
    unit = _column(header, "Jm", 48, bold=True)
    quantity = _column(header, "Ilość", 64, bold=True)
    price = _column(header, "Cena netto", 88, bold=True)
    net = _column(header, "Wartość netto", 100, bold=True)
    vat = _column(header, "VAT", 48, bold=True)
    row = wx.BoxSizer(wx.HORIZONTAL)
    row.Add(number, flag=wx.RIGHT, border=6)
    row.Add((20, 14))
    row.Add(name, flag=wx.RIGHT, border=8)
    for label in (index, unit, quantity, price, net):
        row.Add(label, flag=wx.RIGHT, border=8)
    row.Add(vat)
    header.SetSizer(row)
    return header


class _LineRow(wx.Panel):
    def __init__(self, parent, line_index: int, line, replacement: CatalogItem | None, manual: bool, assign, clear):
        super().__init__(parent)
        self.SetBackgroundColour(wx.WHITE)
        self._line_index = line_index
        self._assign = assign
        self._clear = clear
        self._original_name = line.name
        self._original_index = line.index
        self._assigned: CatalogItem | None = None
        self._matches: tuple[CatalogItem, ...] = ()

        number = _column(self, line.number or str(line_index + 1), 36, bold=True)
        self._dot = wx.Panel(self, size=(14, 14))
        self._name = _column(self, line.name, 280)
        self._index = _column(self, line.index, 90)
        unit = _column(self, line.unit or "—", 48)
        quantity = _column(self, line.quantity or "—", 64)
        price = _column(self, line.unit_price or "—", 88)
        net = _column(self, line.net_value or "—", 100)
        vat = _column(self, line.vat_rate or "—", 48)

        self._mark = wx.Button(self, label="+", size=(36, -1))
        self._mark.Bind(wx.EVT_BUTTON, self._on_mark)
        self._search = wx.TextCtrl(self, style=wx.TE_PROCESS_ENTER)
        self._search.Bind(wx.EVT_TEXT, self._on_type)
        self._search.Bind(wx.EVT_TEXT_ENTER, self._add)
        self._search.Bind(wx.EVT_KEY_DOWN, self._on_key)
        add = wx.Button(self, label="Dodaj")
        add.Bind(wx.EVT_BUTTON, self._add)

        identity = wx.BoxSizer(wx.HORIZONTAL)
        identity.Add(number, flag=wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, border=6)
        identity.Add(self._dot, flag=wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, border=6)
        identity.Add(self._name, flag=wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, border=8)
        for label in (self._index, unit, quantity, price, net):
            identity.Add(label, flag=wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, border=8)
        identity.Add(vat, flag=wx.ALIGN_CENTER_VERTICAL)

        search_row = wx.BoxSizer(wx.HORIZONTAL)
        search_row.Add(self._mark, flag=wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, border=6)
        search_row.Add(self._search, proportion=1, flag=wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, border=6)
        search_row.Add(add, flag=wx.ALIGN_CENTER_VERTICAL)

        rule = wx.Panel(self, size=(-1, 1))
        rule.SetBackgroundColour(wx.Colour(220, 220, 220))

        root = wx.BoxSizer(wx.VERTICAL)
        root.Add(identity, flag=wx.EXPAND)
        root.Add(search_row, flag=wx.EXPAND | wx.LEFT | wx.TOP, border=2)
        root.Add(rule, flag=wx.EXPAND | wx.TOP, border=4)
        self.SetSizer(root)
        self._paint(replacement, manual)

    def _paint(self, item: CatalogItem | None, manual: bool = True):
        self._assigned = item
        if item is None:
            self._name.SetLabel(self._original_name)
            self._index.SetLabel(self._original_index)
            self._dot.SetBackgroundColour(RED)
            self._mark.SetLabel("+")
            self._dot.Refresh()
            return
        self._name.SetLabel(f"{item.name} ({self._original_name})")
        self._index.SetLabel(item.code)
        self._dot.SetBackgroundColour(GREEN if manual else YELLOW)
        self._mark.SetLabel("−")
        self._search.ChangeValue(self._choice_text(item))
        self._dot.Refresh()

    def _choice_text(self, item: CatalogItem) -> str:
        return f"{item.code}  {item.name}"

    def _suggest(self) -> "_SuggestList":
        parent = self.GetParent()
        while parent is not None and not isinstance(parent, EditFrame):
            parent = parent.GetParent()
        return parent._suggest

    def _on_key(self, event):
        suggest = self._suggest()
        if suggest.belongs_to(self) and suggest.move(event.GetKeyCode()):
            return
        event.Skip()

    def _on_mark(self, _event):
        if self._assigned is not None:
            self._remove()
            return
        self._add(_event)

    def _on_type(self, _event):
        query = self._search.GetValue().strip()
        if self._assigned is not None and query == self._choice_text(self._assigned):
            return
        if not query:
            if self._assigned is not None:
                self._remove()
            else:
                self._matches = ()
                self._suggest().hide(self)
            return
        try:
            found = list_goods(query)
        except OSError:
            wx.MessageBox(
                "Nie udało się odczytać bazy towarów.",
                "Subksef",
                wx.OK | wx.ICON_WARNING,
            )
            return
        self._matches = tuple(
            sorted(found, key=lambda item: (_rank(item, query), item.code.casefold()))[:MATCH_LIMIT]
        )
        if not self._matches:
            self._suggest().hide(self)
            return
        self._suggest().present(
            self,
            self._search,
            [f"{item.code}  {item.name}" for item in self._matches],
        )

    def _add(self, _event):
        if not self._matches:
            if self._assigned is not None and self._search.GetValue() == self._choice_text(self._assigned):
                return
            wx.MessageBox(
                "Nie ma takiego towaru w bazie.",
                "Subksef",
                wx.OK | wx.ICON_INFORMATION,
            )
            return
        selected = self._suggest().selection(self)
        item = self._matches[selected if selected != wx.NOT_FOUND else 0]
        if not self._assign(self._line_index, item):
            return
        self._matches = ()
        self._suggest().hide(self)
        self._paint(item)

    def _remove(self):
        if not self._clear(self._line_index):
            return
        self._matches = ()
        self._suggest().hide(self)
        self._search.ChangeValue("")
        self._paint(None)

    def _relayout(self):
        self.Layout()
        parent = self.GetParent()
        while parent is not None and not isinstance(parent, EditFrame):
            parent = parent.GetParent()
        if isinstance(parent, EditFrame):
            parent._relayout()


class _SuggestList(wx.Frame):
    def __init__(self, parent: EditFrame):
        super().__init__(
            parent,
            style=wx.FRAME_FLOAT_ON_PARENT | wx.FRAME_NO_TASKBAR | wx.BORDER_SIMPLE,
        )
        self.SetBackgroundColour(wx.WHITE)
        self._list = wx.ListBox(self, style=wx.LB_SINGLE)
        self._owner: _LineRow | None = None
        self._anchor: wx.Window | None = None
        box = wx.BoxSizer(wx.VERTICAL)
        box.Add(self._list, proportion=1, flag=wx.EXPAND)
        self.SetSizer(box)
        self._list.Bind(wx.EVT_LISTBOX_DCLICK, self._activate)
        self._list.Bind(wx.EVT_KEY_DOWN, self._on_key)

    def present(self, owner: "_LineRow", anchor: wx.Window, labels: list[str]):
        self._owner = owner
        self._anchor = anchor
        self._list.SetItems(labels)
        self._list.SetSelection(0)
        self._place(anchor)
        self.Show()
        wx.CallAfter(anchor.SetFocus)

    def hide(self, owner: "_LineRow | None" = None):
        if owner is not None and self._owner is not owner:
            return
        self._owner = None
        self._anchor = None
        self.Hide()

    def belongs_to(self, owner: "_LineRow") -> bool:
        return self.IsShown() and self._owner is owner

    def selection(self, owner: "_LineRow") -> int:
        if not self.belongs_to(owner):
            return 0
        return self._list.GetSelection()

    def move(self, key: int) -> bool:
        if key not in {wx.WXK_DOWN, wx.WXK_UP, wx.WXK_NUMPAD_DOWN, wx.WXK_NUMPAD_UP}:
            return False
        count = self._list.GetCount()
        if count == 0:
            return False
        current = self._list.GetSelection()
        if current == wx.NOT_FOUND:
            current = 0
        step = 1 if key in {wx.WXK_DOWN, wx.WXK_NUMPAD_DOWN} else -1
        self._list.SetSelection(max(0, min(count - 1, current + step)))
        return True

    def follow(self):
        if self.IsShown() and self._anchor is not None:
            self._place(self._anchor)

    def _activate(self, _event):
        if self._owner is not None:
            self._owner._add(_event)

    def _on_key(self, event):
        if event.GetKeyCode() in {wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER} and self._owner is not None:
            self._owner._add(event)
            return
        event.Skip()

    def _place(self, anchor: wx.Window):
        frame = self.GetParent()
        safe_origin = frame._scroll.ClientToScreen((0, 0))
        safe_size = frame._scroll.GetClientSize()
        safe_bottom = safe_origin.y + safe_size.y
        row_height = self._list.GetCharHeight() + 8
        count = max(self._list.GetCount(), 1)
        height = count * row_height + 4
        width = anchor.GetSize().width
        field_top = anchor.ClientToScreen((0, 0))
        field_bottom = anchor.ClientToScreen((0, anchor.GetSize().height))
        room_below = safe_bottom - field_bottom.y
        room_above = field_top.y - safe_origin.y
        if room_below >= height or room_below >= room_above:
            y = field_bottom.y
            height = min(height, max(row_height + 4, room_below))
        else:
            height = min(height, max(row_height + 4, room_above))
            y = field_top.y - height
        x = min(max(field_bottom.x, safe_origin.x), safe_origin.x + safe_size.x - width)
        self.SetSize(x, y, max(width, 120), height)
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
