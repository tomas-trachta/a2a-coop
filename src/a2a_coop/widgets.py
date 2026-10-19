import tkinter as tk
from tkinter import font, ttk
from typing import Callable, NamedTuple, Optional

from . import theme

Segment = tuple[str, tuple[str, ...]]
CARD_PADDING = 12


class Row(NamedTuple):
    iid: str
    values: tuple
    tags: tuple = ()
    text: str = ""
    image: object = ""


class Column(NamedTuple):
    name: str
    heading: str
    width: int
    stretch: bool = True
    shown: bool = True


class TextPanel:
    def __init__(self, parent: tk.Misc, height: int):
        self.frame, self.text = scrolled_text(parent, height)
        self.shown: Optional[tuple[Segment, ...]] = None

    def show(self, segments: tuple[Segment, ...]) -> None:
        if segments == self.shown:
            return

        self.shown = segments
        clear_text(self.text)

        for content, tags in segments:
            append_text(self.text, content, tags)

    def content(self) -> str:
        return self.text.get("1.0", "end-1c")


class SashPlacer:
    def __init__(self, paned: ttk.PanedWindow, positions: Callable[[int], tuple[int, ...]]):
        self.paned = paned
        self.positions = positions
        self.moved = False

        paned.bind("<Configure>", lambda event: self.place(), add="+")
        paned.bind("<ButtonRelease-1>", lambda event: self.mark_moved(), add="+")

    def mark_moved(self) -> None:
        self.moved = True

    def reset(self) -> None:
        self.moved = False
        self.place()

    def place(self) -> None:
        length = self.length()

        if self.moved or length <= 1:
            return

        wanted = self.positions(length)

        for _ in range(2):
            for index, position in enumerate(wanted):
                self.paned.sashpos(index, position)

    def length(self) -> int:
        if str(self.paned.cget("orient")) == "horizontal":
            return self.paned.winfo_width()

        return self.paned.winfo_height()


def card(parent: tk.Misc) -> ttk.Frame:
    return ttk.Frame(parent, style="Card.TFrame", padding=CARD_PADDING)


def surface(parent: tk.Misc) -> ttk.Frame:
    return ttk.Frame(parent, style="Surface.TFrame")


def section_header(parent: tk.Misc, title: str) -> tuple[ttk.Frame, ttk.Label]:
    header = surface(parent)
    header.pack(side="top", fill="x", pady=(0, 8))

    label = ttk.Label(header, text=title, style="Heading.Card.TLabel")
    label.pack(side="left")

    return header, label


def button_row(parent: tk.Misc, side: str = "top", pady: tuple[int, int] = (10, 0)) -> ttk.Frame:
    row = surface(parent)
    row.pack(side=side, fill="x", pady=pady)

    return row


def add_button(parent: tk.Misc, label: str, command: Callable[[], object], primary: bool = False, **placement) -> ttk.Button:
    button = ttk.Button(parent, text=label, command=command, style="Primary.TButton" if primary else "TButton")
    button.pack(**(placement or {"side": "left", "padx": (0, 6)}))

    return button


def wrapping_label(parent: tk.Misc, style: str = "Muted.Card.TLabel", **placement) -> ttk.Label:
    label = ttk.Label(parent, style=style, justify="left", anchor="nw")
    label.pack(**(placement or {"side": "top", "fill": "x"}))
    label.bind("<Configure>", lambda event: label.configure(wraplength=max(event.width - 4, 100)))

    return label


def scrolled_tree(
    parent: tk.Misc,
    columns: tuple[Column, ...],
    height: int,
    headings: bool = False,
    tree_column: Optional[Column] = None,
) -> ttk.Treeview:
    frame = surface(parent)
    frame.pack(side="top", fill="both", expand=True)

    tree = ttk.Treeview(
        frame,
        columns=[column.name for column in columns],
        height=height,
        show=tree_parts(headings, tree_column is not None),
        selectmode="browse",
        displaycolumns=[column.name for column in columns if column.shown],
    )
    scrollbar = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
    tree.configure(yscrollcommand=autohiding(scrollbar))

    tree.pack(side="left", fill="both", expand=True)
    name_columns(tree, columns if tree_column is None else (tree_column, *columns))

    return tree


def tree_parts(headings: bool, tree_column: bool) -> str:
    return " ".join(part for part, wanted in (("tree", tree_column), ("headings", headings)) if wanted)


def swatch_image(master: tk.Misc, color: str, size: int, gap: int) -> tk.PhotoImage:
    image = tk.PhotoImage(master=master, width=size + gap, height=size)
    image.put(color, to=(0, 0, size, size))

    return image


def name_columns(tree: ttk.Treeview, columns: tuple[Column, ...]) -> None:
    for column in columns:
        tree.heading(column.name, text=column.heading, anchor="w")
        tree.column(column.name, width=column.width, minwidth=32, stretch=column.stretch, anchor="w")


def color_tags(tree: ttk.Treeview, colors: dict[str, str]) -> None:
    for tag, color in colors.items():
        tree.tag_configure(tag, foreground=color)


def scrolled_text(
    parent: tk.Misc, height: int, on_scroll: Optional[Callable[[float, float], None]] = None
) -> tuple[ttk.Frame, tk.Text]:
    frame = surface(parent)

    options = theme.text_options(theme.current(parent))
    text = tk.Text(frame, height=height, wrap="word", state="disabled", padx=0, pady=0, takefocus=0, **options)
    scrollbar = ttk.Scrollbar(frame, orient="vertical", command=text.yview)
    text.configure(yscrollcommand=autohiding(scrollbar, on_scroll))

    text.pack(side="left", fill="both", expand=True)
    text.bind("<1>", lambda event: text.focus_set(), add="+")
    text.bind("<<Selection>>", lambda event: text.tag_raise("sel"), add="+")

    return frame, text


def field_text(parent: tk.Misc, height: int) -> tuple[ttk.Frame, tk.Text]:
    frame = surface(parent)

    text = tk.Text(frame, height=height, wrap="word", undo=True, **theme.field_text_options(theme.current(parent)))
    scrollbar = ttk.Scrollbar(frame, orient="vertical", command=text.yview)
    text.configure(yscrollcommand=autohiding(scrollbar))

    text.pack(side="left", fill="both", expand=True)

    return frame, text


def display_lines(text: tk.Text) -> int:
    counted = text.tk.call(str(text), "count", "-update", "-displaylines", "1.0", "end-1c")

    return int(counted or 0) + 1


def autohiding(
    scrollbar: ttk.Scrollbar, on_scroll: Optional[Callable[[float, float], None]] = None
) -> Callable[[str, str], None]:
    def update(first: str, last: str) -> None:
        scrollbar.set(first, last)
        show_when(scrollbar, float(first) > 0 or float(last) < 1)

        if on_scroll is not None:
            on_scroll(float(first), float(last))

    return update


def show_when(scrollbar: ttk.Scrollbar, needed: bool) -> None:
    shown = bool(scrollbar.winfo_manager())

    if needed and not shown:
        scrollbar.pack(side="right", fill="y", before=scrollbar.master.pack_slaves()[0])
    elif shown and not needed:
        scrollbar.pack_forget()


def recolor_widgets(widget: tk.Misc, palette: theme.Palette) -> None:
    recolor_widget(widget, palette)

    for child in widget.winfo_children():
        recolor_widgets(child, palette)


def recolor_widget(widget: tk.Misc, palette: theme.Palette) -> None:
    if isinstance(widget, (tk.Tk, tk.Toplevel)):
        widget.configure(background=palette.background)
    elif isinstance(widget, tk.Text):
        recolor_text(widget, palette)
    elif isinstance(widget, tk.Menu):
        widget.configure(**theme.menu_options(palette))
    elif isinstance(widget, ttk.Combobox):
        recolor_popdown(widget, palette)


def recolor_text(text: tk.Text, palette: theme.Palette) -> None:
    is_field = int(text.cget("highlightthickness")) > 0

    text.configure(**(theme.field_text_options(palette) if is_field else theme.text_options(palette)))


def recolor_popdown(combobox: ttk.Combobox, palette: theme.Palette) -> None:
    popdown = combobox.tk.call("ttk::combobox::PopdownWindow", str(combobox))
    listbox = f"{popdown}.f.l"

    for option, value in theme.listbox_options(palette).items():
        combobox.tk.call(listbox, "configure", f"-{option.lower()}", value)


def set_enabled(widget: ttk.Widget, enabled: bool) -> None:
    widget.state(["!disabled"] if enabled else ["disabled"])


def set_field_enabled(text: tk.Text, enabled: bool) -> None:
    palette = theme.current(text)

    text.configure(state="normal" if enabled else "disabled", background=palette.surface if enabled else palette.background)


def selected_iid(tree: ttk.Treeview) -> Optional[str]:
    selection = tree.selection()

    return selection[0] if selection else None


def sync_rows(tree: ttk.Treeview, rows: list[Row]) -> None:
    wanted = {row.iid for row in rows}
    stale = [iid for iid in tree.get_children() if iid not in wanted]

    if stale:
        tree.delete(*stale)

    for index, row in enumerate(rows):
        place_row(tree, index, row)


def place_row(tree: ttk.Treeview, index: int, row: Row) -> None:
    if not tree.exists(row.iid):
        tree.insert("", index, iid=row.iid, text=row.text, image=row.image, values=row.values, tags=row.tags)
        return

    tree.item(row.iid, text=row.text, image=row.image, values=row.values, tags=row.tags)

    if tree.index(row.iid) != index:
        tree.move(row.iid, "", index)


def select_first(tree: ttk.Treeview) -> None:
    rows = tree.get_children()

    if rows and not tree.selection():
        tree.selection_set(rows[0])


def select_only(tree: ttk.Treeview, iid: str) -> None:
    if tree.exists(iid) and tree.selection() != (iid,):
        tree.selection_set(iid)
        tree.see(iid)


def clear_text(text: tk.Text) -> None:
    text.configure(state="normal")
    text.delete("1.0", "end")
    text.configure(state="disabled")


def append_text(text: tk.Text, content: str, tags: tuple[str, ...] = ()) -> None:
    text.configure(state="normal")
    text.insert("end", content, tags)
    text.configure(state="disabled")


def is_scrolled_to_end(text: tk.Text) -> bool:
    return text.yview()[1] >= 0.999


def clip_to_lines(text: str, font_name: str, width: int, lines: int) -> str:
    measure = font.nametofont(font_name).measure
    room = width * lines * 0.9

    if width <= 1 or measure(text) <= room:
        return text

    return text[: longest_fitting_prefix(text, lambda prefix: measure(prefix + "…") <= room)].rstrip() + "…"


def longest_fitting_prefix(text: str, fits: Callable[[str], bool]) -> int:
    low, high = 0, len(text)

    while low < high:
        middle = (low + high + 1) // 2

        if fits(text[:middle]):
            low = middle
        else:
            high = middle - 1

    return low


def replace_selection(text: tk.Text, content: str) -> None:
    if text.tag_ranges("sel") and text.compare("sel.first", "<=", "insert") and text.compare("sel.last", ">=", "insert"):
        text.delete("sel.first", "sel.last")

    text.insert("insert", content)


def insert_block(text: tk.Text, block: str) -> None:
    if text.tag_ranges("sel"):
        replace_selection(text, "")

    lead = "" if text.compare("insert", "==", "insert linestart") else "\n"
    text.insert("insert", f"{lead}{block}\n")
    text.see("insert")


def selected_text(text: tk.Text) -> str:
    return text.get("sel.first", "sel.last") if text.tag_ranges("sel") else ""


def bind_select_all(root: tk.Misc) -> None:
    for widget_class in ("Text", "TEntry"):
        for variant in ("a", "A"):
            root.bind_class(widget_class, f"<Control-{variant}>", select_all)


def select_all(event: tk.Event) -> str:
    widget = event.widget

    if isinstance(widget, tk.Text):
        widget.tag_add("sel", "1.0", "end-1c")
    else:
        widget.event_generate("<<SelectAll>>")

    return "break"


def focus_next(widget: tk.Misc) -> str:
    widget.tk_focusNext().focus_set()

    return "break"


def focus_previous(widget: tk.Misc) -> str:
    widget.tk_focusPrev().focus_set()

    return "break"
