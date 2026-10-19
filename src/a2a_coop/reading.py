import tkinter as tk
from tkinter import font
from typing import Optional

from pygments.lexer import Lexer
from pygments.lexers import get_lexer_by_name
from pygments.token import Comment, Keyword, Name, Number, String
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
SYNTAX_TAG = "syntax:"
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

    text.tag_configure("body", font=regular, lmargin1=indent, lmargin2=indent, spacing1=3, spacing2=LINE_SPACING)
    text.tag_configure("body-code-block", font=theme.CODE_FONT, background=palette.code_background, spacing1=1, spacing2=1)
    text.tag_configure("body-code", font=theme.CODE_FONT, background=palette.code_background)
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
    segments = [*code_segments(line.spans[0].text, line.language, tags), ("\n", tags)]

    if line.gap:
        content, first_tags = segments[0]
        head, newline, rest = content.partition("\n")
        segments[0:1] = [(head, (*first_tags, "body-gap")), *([(newline + rest, first_tags)] if newline else [])]

    return [segment for segment in segments if segment[0]]


def code_segments(code: str, language: str, tags: tuple[str, ...]) -> list[Segment]:
    lexer = lexer_for(language)

    if lexer is None:
        return [(code, tags)]

    segments: list[Segment] = []

    for token, value in lexer.get_tokens(code):
        kind = syntax_kind(token)
        segments.append((value, (*tags, f"{SYNTAX_TAG}{kind}") if kind else tags))

    if segments and segments[-1][0].endswith("\n"):
        value, segment_tags = segments.pop()
        segments.append((value[:-1], segment_tags))

    return [segment for segment in segments if segment[0]]


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
