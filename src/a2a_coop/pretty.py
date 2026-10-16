import zlib
from typing import Iterable

from rich import box
from rich.console import RenderableType
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from . import render
from .models import Message
from .store import EVENT, EVERYONE, QUESTION, USER

AGENT_COLORS = ("cyan", "magenta", "yellow", "blue", "bright_red", "bright_cyan", "bright_magenta")
USER_COLOR = "bright_green"
EVERYONE_COLOR = "white"
QUESTION_COLOR = "bright_yellow"


def participant_color(name: str) -> str:
    if name == USER:
        return USER_COLOR

    if name == EVERYONE:
        return EVERYONE_COLOR

    return AGENT_COLORS[zlib.crc32(name.encode()) % len(AGENT_COLORS)]


def participant(name: str) -> Text:
    label = "everyone" if name == EVERYONE else name

    return Text(label, style=f"bold {participant_color(name)}")


def message(item: Message) -> RenderableType:
    if item.kind == EVENT:
        return event(item)

    return chat(item)


def messages(items: Iterable[Message]) -> list[RenderableType]:
    return [message(item) for item in items]


def chat(item: Message) -> Panel:
    is_question = item.kind == QUESTION

    return Panel(
        Markdown(item.body),
        title=chat_title(item),
        title_align="left",
        subtitle=chat_subtitle(item),
        subtitle_align="right",
        border_style=QUESTION_COLOR if is_question else participant_color(item.sender),
        box=box.HEAVY if item.recipient == USER else box.ROUNDED,
        padding=(0, 1),
    )


def chat_title(item: Message) -> Text:
    verb = " asks " if item.kind == QUESTION else " → "
    marker = ("? ", f"bold {QUESTION_COLOR}") if item.kind == QUESTION else ("", "")

    return Text.assemble(" ", marker, participant(item.sender), (verb, "dim"), participant(item.recipient), " ")


def chat_subtitle(item: Message) -> Text:
    number = f"#{item.id} · " if item.kind == QUESTION else ""

    return Text(f"{number}{render.clock(item.created_at)}", style="dim")


def event(item: Message) -> Table:
    body = Text(item.body, style="dim")
    body.highlight_words([item.sender], style=participant_color(item.sender))

    table = Table.grid(padding=(0, 1), expand=True)
    table.add_column(no_wrap=True, style="dim")
    table.add_column(no_wrap=True, style="dim")
    table.add_column(ratio=1)
    table.add_row(render.clock(item.created_at), "•", body)

    return table

