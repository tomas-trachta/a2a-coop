import tkinter as tk
from tkinter import font
from typing import Optional

from pygments.lexer import Lexer
from pygments.lexers import get_lexer_by_name
from pygments.token import Comment, Keyword, Name, Number, String, Text
from pygments.util import ClassNotFound

from . import markup, theme
from .widgets import Segment

LIST_STEP = 18
LINE_SPACING = 4
PARAGRAPH_GAP = 10
MEASURE_CHARACTERS = 96
MEASURE_SAMPLE = "abcdefghijklmnopqrstuvwxyz"
LIST_TAG = "list:"
STYLE_TAGS = {"strong": "body-strong", "code": "body-code"}
LINE_TAGS = {"heading": "body-heading", "code": "body-code-block"}
CODE_EDGE_TAGS = ("body-code-first", "body-code-last")
CODE_PADDING = 6
SYNTAX_TAG = "syntax:"
PLAIN_TEXT = "Plain text"
CODE_LANGUAGES = {
    PLAIN_TEXT: "",
    "Bash": "bash",
    "C": "c",
    "C#": "csharp",
    "C++": "cpp",
    "CSS": "css",
    "Dart": "dart",
    "Dockerfile": "docker",
    "Elixir": "elixir",
    "Go": "go",
    "Haskell": "haskell",
    "HTML": "html",
    "Java": "java",
    "JavaScript": "javascript",
    "JSON": "json",
    "Kotlin": "kotlin",
    "Lua": "lua",
    "Markdown": "markdown",
    "Perl": "perl",
    "PHP": "php",
    "PowerShell": "powershell",
    "Python": "python",
    "R": "r",
    "Ruby": "ruby",
    "Rust": "rust",
    "Scala": "scala",
    "SQL": "sql",
    "Swift": "swift",
    "TypeScript": "typescript",
    "XML": "xml",
    "YAML": "yaml",
}
SYNTAX_TOKENS = (
    (Comment, "comment"),
    (String, "string"),
    (Number, "number"),
    (Keyword, "keyword"),
    (Name.Builtin, "builtin"),
    (Name.Function, "function"),
    (Name.Class, "function"),
    (Name.Decorator, "function"),
)


def configure_reading_tags(text: tk.Text, palette: theme.Palette, indent: int = 0, large: bool = True) -> None:
    regular, bold = (theme.READING_FONT, theme.READING_BOLD_FONT) if large else (theme.TEXT_FONT, theme.BOLD_FONT)

    text.tag_configure(
        "body",
        font=regular,
        lmargin1=indent,
        lmargin2=indent,
        spacing1=3,
        spacing2=LINE_SPACING,
        rmargincolor=palette.surface,
    )
    text.tag_configure("body-code-block", font=theme.CODE_FONT, background=palette.code_background, spacing1=1, spacing2=1)
    text.tag_configure("body-code-first", spacing1=CODE_PADDING)
    text.tag_configure("body-code-last", spacing3=CODE_PADDING)
    text.tag_configure("body-code", font=theme.CODE_FONT, foreground=palette.inline_code)
    text.tag_configure("body-heading", font=theme.READING_HEADING_FONT if large else bold)
    text.tag_configure("body-strong", font=bold)
    text.tag_configure("body-gap", spacing1=PARAGRAPH_GAP)

    for kind, color in palette.syntax.items():
        text.tag_configure(f"{SYNTAX_TAG}{kind}", foreground=color)


def body_segments(text: tk.Text, body: str, base: tuple[str, ...] = ("body",)) -> list[Segment]:
    segments: list[Segment] = []

    for line in markup.parse(body):
        if line.kind == "code":
            segments.extend(code_block(line, base))
            continue

        tags = (*base, *line_tags(text, line))

        if line.marker and not line.continued:
            segments.append((f"{line.marker}\t", tags))

        segments.extend((span.text, (*tags, STYLE_TAGS[span.style]) if span.style else tags) for span in line.spans)
        segments.append(("\n", tags))

    return segments


def code_block(line: markup.Line, base: tuple[str, ...]) -> list[Segment]:
    tags = (*base, LINE_TAGS["code"])
    rows = code_rows(line.spans[0].text, line.language)
    segments: list[Segment] = []

    for index, row in enumerate(rows):
        row_tags = (*tags, *code_edges(index, len(rows)))

        segments.extend((value, (*row_tags, f"{SYNTAX_TAG}{kind}") if kind else row_tags) for value, kind in row)
        segments.append(("\n", row_tags))

    return [segment for segment in segments if segment[0]]


def code_edges(index: int, count: int) -> tuple[str, ...]:
    first, last = CODE_EDGE_TAGS

    return tuple(tag for tag, edge in ((first, index == 0), (last, index == count - 1)) if edge)


def code_rows(code: str, language: str) -> list[list[tuple[str, str]]]:
    lexer = lexer_for(language)
    tokens = lexer.get_tokens(code) if lexer else [(Text, code)]
    rows: list[list[tuple[str, str]]] = [[]]

    for token, value in tokens:
        kind = syntax_kind(token)
        first, *more = value.split("\n")
        rows[-1].append((first, kind))
        rows.extend([(part, kind)] for part in more)

    if len(rows) > 1 and not any(value for value, kind in rows[-1]):
        rows.pop()

    return rows


def lexer_for(language: str) -> Optional[Lexer]:
    if not language:
        return None

    try:
        return get_lexer_by_name(language, stripnl=False, ensurenl=False)
    except ClassNotFound:
        return None


def syntax_kind(token: tuple) -> str:
    return next((kind for family, kind in SYNTAX_TOKENS if token in family), "")


def line_tags(text: tk.Text, line: markup.Line) -> tuple[str, ...]:
    tags = ("body-gap",) if line.gap else ()

    if line.kind == "item":
        return (*tags, list_tag(text, line))

    return (*tags, LINE_TAGS[line.kind]) if line.kind in LINE_TAGS else tags


def list_tag(text: tk.Text, line: markup.Line) -> str:
    start = int(text.tag_cget("body", "lmargin1") or 0) + line.level * LIST_STEP
    hang = body_font(text).measure(f"{line.marker}  ")
    first = start + hang if line.continued else start
    tag = f"{LIST_TAG}{first}:{start + hang}"

    text.tag_configure(tag, lmargin1=first, lmargin2=start + hang, tabs=(start + hang,))

    return tag


def body_font(text: tk.Text) -> font.Font:
    return font.nametofont(text.tag_cget("body", "font") or theme.TEXT_FONT, root=text)


def cap_line_length(text: tk.Text, tags: tuple[str, ...] = ("body",), minimum_margin: int = 4) -> None:
    def fit(width: int) -> None:
        indent = int(text.tag_cget("body", "lmargin1") or 0)
        average = body_font(text).measure(MEASURE_SAMPLE) / len(MEASURE_SAMPLE)
        margin = max(minimum_margin, width - indent - round(average * MEASURE_CHARACTERS))

        for tag in tags:
            text.tag_configure(tag, rmargin=margin)

    text.bind("<Configure>", lambda event: fit(event.width), add="+")
