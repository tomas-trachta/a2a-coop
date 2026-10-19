import colorsys
import tkinter as tk
from dataclasses import dataclass
from tkinter import font, ttk

BODY_FONT = "TkDefaultFont"
TEXT_FONT = "TkTextFont"
FIXED_FONT = "TkFixedFont"
BOLD_FONT = "CoopBold"
GOAL_TITLE_FONT = "CoopGoalTitle"
TITLE_FONT = "CoopTitle"
READING_FONT = "CoopReading"
READING_BOLD_FONT = "CoopReadingBold"
READING_HEADING_FONT = "CoopReadingHeading"
CODE_FONT = "CoopCode"

MIN_BODY_POINTS = 10
GOAL_TITLE_SCALE = 1.3
TITLE_SCALE = 1.7
READING_SCALE = 1.1
READING_HEADING_SCALE = 1.2
REFERENCE_DPI = 96
PANE_GAP = 12

GOLDEN_TURN = 0.381966
DERIVED_SATURATION = 0.65
APPEARANCE_VARIABLE = "a2a_coop_appearance"


@dataclass(frozen=True)
class Palette:
    name: str
    background: str
    surface: str
    text: str
    secondary: str
    disabled_text: str
    border: str
    hover: str
    scroll_thumb: str
    scroll_thumb_hover: str
    primary: str
    primary_hover: str
    primary_disabled: str
    on_primary: str
    on_primary_disabled: str
    selected: str
    selected_text: str
    success: str
    warning: str
    question_background: str
    error: str
    user: str
    everyone: str
    code_background: str
    syntax: dict[str, str]
    identities: tuple[str, ...]
    derived_lightness: float


LIGHT = Palette(
    name="light",
    background="#F3F5F9",
    surface="#FFFFFF",
    text="#182230",
    secondary="#526174",
    disabled_text="#8D99A8",
    border="#D6DEE8",
    hover="#EEF2F8",
    scroll_thumb="#C4CEDA",
    scroll_thumb_hover="#A3B1C2",
    primary="#2457C5",
    primary_hover="#1D46A0",
    primary_disabled="#A7BBE6",
    on_primary="#FFFFFF",
    on_primary_disabled="#FFFFFF",
    selected="#E7EEFF",
    selected_text="#182230",
    success="#21633B",
    warning="#8A4B08",
    question_background="#FFF4DB",
    error="#B42318",
    user="#1E7B45",
    everyone="#344054",
    code_background="#EEF2F7",
    syntax={
        "keyword": "#CF222E",
        "string": "#0A3069",
        "comment": "#57606A",
        "number": "#0550AE",
        "function": "#6639BA",
        "builtin": "#953800",
    },
    identities=(
        "#1D4ED8",
        "#C2410C",
        "#7C3AED",
        "#0F766E",
        "#BE123C",
        "#A16207",
        "#A21CAF",
        "#0E7490",
        "#4D7C0F",
        "#92400E",
        "#4338CA",
        "#6B21A8",
    ),
    derived_lightness=0.3,
)

DARK = Palette(
    name="dark",
    background="#0E1624",
    surface="#172233",
    text="#E5EDF7",
    secondary="#A9B8CC",
    disabled_text="#778599",
    border="#35445B",
    hover="#233149",
    scroll_thumb="#4B5C76",
    scroll_thumb_hover="#687D9E",
    primary="#94B8FF",
    primary_hover="#B4CCFF",
    primary_disabled="#344762",
    on_primary="#101A2B",
    on_primary_disabled="#A9B8CC",
    selected="#294269",
    selected_text="#E5EDF7",
    success="#86D6A0",
    warning="#F6C66D",
    question_background="#382A15",
    error="#FDA4AF",
    user="#86D6A0",
    everyone="#CBD5E1",
    code_background="#0B1220",
    syntax={
        "keyword": "#FF7B72",
        "string": "#A5D6FF",
        "comment": "#8B949E",
        "number": "#79C0FF",
        "function": "#D2A8FF",
        "builtin": "#FFA657",
    },
    identities=(
        "#93B4FF",
        "#FDBA74",
        "#C4B5FD",
        "#5EEAD4",
        "#FDA4AF",
        "#FDE68A",
        "#F0ABFC",
        "#67E8F9",
        "#BEF264",
        "#FDBA8C",
        "#A5B4FC",
        "#D8B4FE",
    ),
    derived_lightness=0.72,
)

PALETTES = {palette.name: palette for palette in (LIGHT, DARK)}


def apply_theme(root: tk.Tk, palette: Palette) -> None:
    root.setvar(APPEARANCE_VARIABLE, palette.name)

    configure_fonts(root)
    configure_styles(ttk.Style(root), root, palette)
    configure_options(root, palette)

    root.configure(background=palette.background)


def current(widget: tk.Misc) -> Palette:
    try:
        return PALETTES[widget.getvar(APPEARANCE_VARIABLE)]
    except (tk.TclError, KeyError):
        return LIGHT


def identity_color(palette: Palette, index: int) -> str:
    if index < len(palette.identities):
        return palette.identities[index]

    hue = (index * GOLDEN_TURN) % 1.0
    channels = colorsys.hls_to_rgb(hue, palette.derived_lightness, DERIVED_SATURATION)

    return "#" + "".join(f"{round(channel * 255):02X}" for channel in channels)


def contrast(foreground: str, background: str) -> float:
    lighter, darker = sorted((luminance(foreground), luminance(background)), reverse=True)

    return (lighter + 0.05) / (darker + 0.05)


def luminance(color: str) -> float:
    red, green, blue = (linear(int(color[index : index + 2], 16) / 255) for index in (1, 3, 5))

    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def linear(channel: float) -> float:
    return channel / 12.92 if channel <= 0.03928 else ((channel + 0.055) / 1.055) ** 2.4


def scaled(widget: tk.Misc, pixels: int) -> int:
    return round(pixels * widget.winfo_fpixels("1i") / REFERENCE_DPI)


def configure_fonts(root: tk.Tk) -> None:
    for name in (BODY_FONT, TEXT_FONT):
        enlarge_font(font.nametofont(name, root=root))

    body = font.nametofont(BODY_FONT, root=root)

    define_font(root, BOLD_FONT, body, weight="bold")
    define_font(root, GOAL_TITLE_FONT, body, weight="bold", scale=GOAL_TITLE_SCALE)
    define_font(root, TITLE_FONT, body, weight="bold", scale=TITLE_SCALE)

    text = font.nametofont(TEXT_FONT, root=root)
    reading_size = round(text.cget("size") * READING_SCALE)

    define_font(root, READING_FONT, text, weight="normal", scale=READING_SCALE)
    define_font(root, READING_BOLD_FONT, text, weight="bold", scale=READING_SCALE)
    define_font(root, READING_HEADING_FONT, text, weight="bold", scale=READING_HEADING_SCALE)
    code_size = reading_size - 1 if reading_size > 0 else reading_size + 1
    define_font(root, CODE_FONT, font.nametofont(FIXED_FONT, root=root), weight="normal", size=code_size)


def enlarge_font(named: font.Font) -> None:
    size = named.cget("size")

    if 0 < size < MIN_BODY_POINTS:
        named.configure(size=MIN_BODY_POINTS)


def define_font(root: tk.Tk, name: str, base: font.Font, weight: str, scale: float = 1.0, size: int = 0) -> None:
    options = ("-family", base.cget("family"), "-size", size or round(base.cget("size") * scale), "-weight", weight)

    if name in font.names(root):
        root.tk.call("font", "configure", name, *options)
        return

    root.tk.call("font", "create", name, *options)


def line_height(root: tk.Tk) -> int:
    return font.nametofont(BODY_FONT, root=root).metrics("linespace")


def configure_styles(style: ttk.Style, root: tk.Tk, palette: Palette) -> None:
    if "clam" in style.theme_names() and style.theme_use() != "clam":
        style.theme_use("clam")

    configure_base(style, palette)
    configure_frames(style, palette)
    configure_labels(style, palette)
    configure_buttons(style, palette)
    configure_checkbuttons(style, palette)
    configure_fields(style, palette)
    configure_trees(style, palette, line_height(root))
    configure_notebooks(style, palette)
    configure_panes(style, palette, scaled(root, PANE_GAP))
    configure_scrollbars(style, palette)


def configure_base(style: ttk.Style, palette: Palette) -> None:
    style.configure(
        ".",
        background=palette.background,
        foreground=palette.text,
        bordercolor=palette.border,
        lightcolor=palette.background,
        darkcolor=palette.background,
        troughcolor=palette.background,
        focuscolor=palette.primary,
        selectbackground=palette.selected,
        selectforeground=palette.selected_text,
        fieldbackground=palette.surface,
        insertcolor=palette.text,
        font=BODY_FONT,
    )
    style.map(".", foreground=[("disabled", palette.disabled_text)])


def configure_frames(style: ttk.Style, palette: Palette) -> None:
    style.configure("Surface.TFrame", background=palette.surface)
    style.configure("Card.TFrame", background=palette.surface, bordercolor=palette.border, relief="solid", borderwidth=1)
    style.configure("TSeparator", background=palette.border)


def configure_labels(style: ttk.Style, palette: Palette) -> None:
    style.configure("TLabel", background=palette.background, foreground=palette.text)
    style.configure("Title.TLabel", font=TITLE_FONT)
    style.configure("Subtitle.TLabel", foreground=palette.secondary)
    style.configure("Field.TLabel", font=BOLD_FONT)
    style.configure("Hint.TLabel", foreground=palette.secondary)
    style.configure("Error.TLabel", foreground=palette.error)
    style.configure("Status.TLabel", foreground=palette.secondary)
    style.configure("Error.Status.TLabel", foreground=palette.error)

    style.configure("Card.TLabel", background=palette.surface)
    style.configure("Muted.Card.TLabel", foreground=palette.secondary)
    style.configure("Field.Card.TLabel", font=BOLD_FONT)
    style.configure("Heading.Card.TLabel", font=BOLD_FONT, padding=(0, 2))
    style.configure(
        "Waiting.Heading.Card.TLabel",
        foreground=palette.warning,
        background=palette.question_background,
        padding=(6, 2),
    )
    style.configure("GoalTitle.Card.TLabel", font=GOAL_TITLE_FONT)


def configure_buttons(style: ttk.Style, palette: Palette) -> None:
    quiet_states = button_states(palette.background, palette.selected, palette.hover)
    primary_states = button_states(palette.primary_disabled, palette.primary_hover, palette.primary_hover)

    style.configure(
        "TButton",
        background=palette.surface,
        foreground=palette.text,
        bordercolor=palette.border,
        lightcolor=palette.surface,
        darkcolor=palette.surface,
        focuscolor=palette.primary,
        padding=(8, 5),
        width=0,
        anchor="center",
    )
    style.map(
        "TButton",
        background=quiet_states,
        lightcolor=quiet_states,
        darkcolor=quiet_states,
        bordercolor=[("focus", palette.primary)],
    )

    style.configure(
        "Primary.TButton",
        background=palette.primary,
        foreground=palette.on_primary,
        bordercolor=palette.primary,
        lightcolor=palette.primary,
        darkcolor=palette.primary,
        focuscolor=palette.on_primary,
    )
    style.map(
        "Primary.TButton",
        background=primary_states,
        lightcolor=primary_states,
        darkcolor=primary_states,
        bordercolor=primary_states,
        foreground=[("disabled", palette.on_primary_disabled)],
    )

    style.configure("Jump.Primary.TButton", padding=(12, 3))


def button_states(disabled: str, pressed: str, active: str) -> list[tuple[str, str]]:
    return [("disabled", disabled), ("pressed", pressed), ("active", active)]


def configure_checkbuttons(style: ttk.Style, palette: Palette) -> None:
    for name, background in (("TCheckbutton", palette.background), ("Card.TCheckbutton", palette.surface)):
        style.configure(
            name,
            background=background,
            foreground=palette.text,
            indicatorbackground=palette.surface,
            indicatorforeground=palette.primary,
            upperbordercolor=palette.border,
            lowerbordercolor=palette.border,
        )
        style.map(name, background=[("active", background)], indicatorbackground=[("pressed", palette.selected)])


def configure_fields(style: ttk.Style, palette: Palette) -> None:
    for name in ("TEntry", "TCombobox"):
        style.configure(
            name,
            fieldbackground=palette.surface,
            background=palette.surface,
            foreground=palette.text,
            bordercolor=palette.border,
            lightcolor=palette.surface,
            darkcolor=palette.surface,
            arrowcolor=palette.secondary,
            insertcolor=palette.text,
            padding=(8, 5),
        )
        style.map(
            name,
            bordercolor=[("focus", palette.primary)],
            lightcolor=[("focus", palette.primary)],
            fieldbackground=[("disabled", palette.background), ("readonly", palette.surface)],
            selectbackground=[("readonly", palette.surface)],
            selectforeground=[("readonly", palette.text)],
        )


def configure_trees(style: ttk.Style, palette: Palette, linespace: int) -> None:
    style.configure(
        "Treeview",
        background=palette.surface,
        fieldbackground=palette.surface,
        foreground=palette.text,
        bordercolor=palette.border,
        lightcolor=palette.surface,
        darkcolor=palette.surface,
        rowheight=linespace + 10,
    )
    style.map(
        "Treeview",
        background=[("selected", palette.selected)],
        foreground=[("selected", palette.selected_text)],
    )

    style.configure(
        "Treeview.Heading",
        background=palette.surface,
        foreground=palette.secondary,
        bordercolor=palette.border,
        lightcolor=palette.surface,
        darkcolor=palette.surface,
        relief="flat",
        padding=(4, 3),
    )
    style.map("Treeview.Heading", background=[("active", palette.hover)], lightcolor=[("active", palette.hover)])


def configure_notebooks(style: ttk.Style, palette: Palette) -> None:
    style.configure(
        "TNotebook",
        background=palette.surface,
        bordercolor=palette.border,
        lightcolor=palette.surface,
        darkcolor=palette.surface,
        tabmargins=(0, 0, 0, 0),
    )
    style.configure(
        "TNotebook.Tab",
        background=palette.background,
        foreground=palette.secondary,
        bordercolor=palette.border,
        lightcolor=palette.background,
        darkcolor=palette.background,
        padding=(14, 5),
    )
    style.map(
        "TNotebook.Tab",
        background=[("selected", palette.surface), ("active", palette.hover)],
        lightcolor=[("selected", palette.primary), ("active", palette.hover)],
        foreground=[("disabled", palette.disabled_text), ("selected", palette.primary)],
        padding=[("selected", (14, 5))],
        expand=[("selected", (0, 2, 0, 0))],
    )


def configure_panes(style: ttk.Style, palette: Palette, gap: int) -> None:
    style.configure("TPanedwindow", background=palette.background)
    style.configure(
        "Sash",
        sashthickness=gap,
        gripcount=0,
        background=palette.background,
        lightcolor=palette.background,
        bordercolor=palette.background,
    )


def configure_scrollbars(style: ttk.Style, palette: Palette) -> None:
    hover_states = [("active", palette.scroll_thumb_hover)]

    for name in ("Vertical.TScrollbar", "Horizontal.TScrollbar"):
        style.configure(
            name,
            background=palette.scroll_thumb,
            troughcolor=palette.surface,
            bordercolor=palette.surface,
            lightcolor=palette.scroll_thumb,
            darkcolor=palette.scroll_thumb,
            arrowcolor=palette.secondary,
            gripcount=0,
        )
        style.map(name, background=hover_states, lightcolor=hover_states, darkcolor=hover_states)


def configure_options(root: tk.Tk, palette: Palette) -> None:
    for option, value in listbox_options(palette).items():
        root.option_add(f"*TCombobox*Listbox.{option}", value)


def listbox_options(palette: Palette) -> dict:
    return {
        "background": palette.surface,
        "foreground": palette.text,
        "selectBackground": palette.selected,
        "selectForeground": palette.selected_text,
        "font": BODY_FONT,
    }


def menu_options(palette: Palette) -> dict:
    return {
        "background": palette.surface,
        "foreground": palette.text,
        "activebackground": palette.selected,
        "activeforeground": palette.selected_text,
        "disabledforeground": palette.disabled_text,
    }


def text_options(palette: Palette) -> dict:
    return {
        "background": palette.surface,
        "foreground": palette.text,
        "selectbackground": palette.selected,
        "selectforeground": palette.selected_text,
        "inactiveselectbackground": palette.selected,
        "insertbackground": palette.text,
        "relief": "flat",
        "borderwidth": 0,
        "highlightthickness": 0,
        "font": TEXT_FONT,
    }


def field_text_options(palette: Palette) -> dict:
    return {
        **text_options(palette),
        "highlightthickness": 1,
        "highlightbackground": palette.border,
        "highlightcolor": palette.primary,
        "padx": 8,
        "pady": 6,
    }
