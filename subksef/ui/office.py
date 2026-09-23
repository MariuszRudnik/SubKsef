import wx

WHITE = wx.Colour(255, 255, 255)
CANVAS = wx.Colour(243, 243, 243)
RIBBON = wx.Colour(245, 245, 245)
BORDER = wx.Colour(225, 225, 225)
ACCENT = wx.Colour(15, 108, 189)
ACCENT_SOFT = wx.Colour(229, 241, 251)
TEXT = wx.Colour(32, 31, 30)
MUTED = wx.Colour(96, 94, 92)


def face(size: int = 9, bold: bool = False) -> wx.Font:
    weight = wx.FONTWEIGHT_BOLD if bold else wx.FONTWEIGHT_NORMAL
    font = wx.Font(size, wx.FONTFAMILY_SWISS, wx.FONTSTYLE_NORMAL, weight, faceName="Segoe UI")
    if font.IsOk():
        return font
    font = wx.SystemSettings.GetFont(wx.SYS_DEFAULT_GUI_FONT)
    font.SetPointSize(size)
    font.SetWeight(weight)
    return font


ICON_SIZE = 24
BUTTON_WIDTH = 104
BUTTON_HEIGHT = 64


def icon(art_id: str, size: int) -> wx.Bitmap:
    bitmap = wx.ArtProvider.GetBitmap(art_id, wx.ART_BUTTON, (size, size))
    if not bitmap.IsOk():
        return wx.Bitmap(size, size)
    if bitmap.GetWidth() != size or bitmap.GetHeight() != size:
        image = bitmap.ConvertToImage().Scale(size, size, wx.IMAGE_QUALITY_HIGH)
        return wx.Bitmap(image)
    return bitmap


class CommandButton(wx.Panel):
    def __init__(self, parent: wx.Window, label: str, art_id: str, handler):
        super().__init__(parent)
        self._handler = handler
        self._enabled = True
        self.SetBackgroundColour(RIBBON)
        picture = wx.StaticBitmap(self, bitmap=icon(art_id, ICON_SIZE))
        self._label = wx.StaticText(self, label=label)
        self._label.SetFont(face(9))
        self._label.SetForegroundColour(TEXT)
        root = wx.BoxSizer(wx.VERTICAL)
        root.Add(picture, flag=wx.ALIGN_CENTER | wx.TOP, border=6)
        root.Add(self._label, flag=wx.ALIGN_CENTER | wx.TOP | wx.BOTTOM, border=4)
        self.SetMinSize((BUTTON_WIDTH, BUTTON_HEIGHT))
        self.SetSizer(root)
        for window in (self, picture, self._label):
            window.Bind(wx.EVT_LEFT_UP, self._click)
            window.Bind(wx.EVT_ENTER_WINDOW, self._enter)
            window.Bind(wx.EVT_LEAVE_WINDOW, self._leave)

    def Enable(self, enable: bool = True):
        self._enabled = enable
        self._label.SetForegroundColour(TEXT if enable else MUTED)
        self.Refresh()

    def _click(self, event):
        if self._enabled:
            self._handler(event)

    def _enter(self, _event):
        if self._enabled:
            self.SetBackgroundColour(ACCENT_SOFT)
            self.Refresh()

    def _leave(self, _event):
        self.SetBackgroundColour(RIBBON)
        self.Refresh()


class RibbonGroup(wx.Panel):
    def __init__(self, parent: wx.Window, title: str):
        super().__init__(parent)
        self.SetBackgroundColour(RIBBON)
        self.buttons = wx.BoxSizer(wx.HORIZONTAL)
        caption = wx.StaticText(self, label=title)
        caption.SetFont(face(8))
        caption.SetForegroundColour(MUTED)
        root = wx.BoxSizer(wx.VERTICAL)
        root.Add(self.buttons, proportion=1, flag=wx.EXPAND | wx.LEFT | wx.RIGHT, border=6)
        root.Add(caption, flag=wx.ALIGN_CENTER | wx.BOTTOM, border=4)
        self.SetSizer(root)

    def add(self, button: CommandButton):
        self.buttons.Add(button, flag=wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, border=4)


class Ribbon(wx.Panel):
    def __init__(self, parent: wx.Window):
        super().__init__(parent)
        self.SetBackgroundColour(RIBBON)
        self._names: list[str] = []
        self._tabs: dict[str, wx.StaticText] = {}
        self._marks: dict[str, wx.Panel] = {}
        self._pages: dict[str, wx.Panel] = {}
        self.on_select = None
        self._tab_row = wx.BoxSizer(wx.HORIZONTAL)
        self._commands = wx.BoxSizer(wx.HORIZONTAL)
        root = wx.BoxSizer(wx.VERTICAL)
        root.Add(self._tab_row, flag=wx.LEFT | wx.TOP, border=8)
        root.Add(self._commands, flag=wx.EXPAND | wx.BOTTOM, border=2)
        self.SetSizer(root)

    def add_page(self, name: str, page: wx.Panel):
        tab = wx.StaticText(self, label=name)
        tab.SetFont(face(10))
        mark = wx.Panel(self, size=(-1, 3))
        tab_box = wx.BoxSizer(wx.VERTICAL)
        tab_box.Add(tab, flag=wx.ALIGN_CENTER | wx.LEFT | wx.RIGHT, border=12)
        tab_box.Add(mark, flag=wx.EXPAND | wx.TOP, border=6)
        self._tab_row.Add(tab_box, flag=wx.RIGHT, border=4)
        tab.Bind(wx.EVT_LEFT_UP, lambda event, page_name=name: self.select(page_name))
        self._names.append(name)
        self._tabs[name] = tab
        self._marks[name] = mark
        self._pages[name] = page
        self._commands.Add(page, proportion=1, flag=wx.EXPAND)
        if len(self._names) == 1:
            self.select(name)
        else:
            page.Hide()
            mark.SetBackgroundColour(RIBBON)

    def select(self, name: str):
        for page_name, page in self._pages.items():
            active = page_name == name
            page.Show(active)
            self._tabs[page_name].SetForegroundColour(ACCENT if active else TEXT)
            self._marks[page_name].SetBackgroundColour(ACCENT if active else RIBBON)
        self.Layout()
        if self.on_select is not None:
            self.on_select(name)
        parent = self.GetParent()
        if parent is not None:
            parent.Layout()


def card(parent: wx.Window) -> tuple[wx.Panel, wx.Panel]:
    outer = wx.Panel(parent)
    outer.SetBackgroundColour(BORDER)
    inner = wx.Panel(outer)
    inner.SetBackgroundColour(WHITE)
    root = wx.BoxSizer(wx.VERTICAL)
    root.Add(inner, proportion=1, flag=wx.EXPAND | wx.ALL, border=1)
    outer.SetSizer(root)
    return outer, inner


def field_label(parent: wx.Window, label: str) -> wx.StaticText:
    text = wx.StaticText(parent, label=label)
    text.SetFont(face(9, bold=True))
    text.SetForegroundColour(TEXT)
    return text
