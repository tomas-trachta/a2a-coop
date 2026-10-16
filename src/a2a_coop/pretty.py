import zlib
from typing import Iterable

from rich import box
from rich.console import Group, RenderableType
from rich.markdown import Markdown
from rich.padding import Padding
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from . import render
from .models import Agent, Goal, Message, Task
from .store import EVENT, EVERYONE, OFFLINE, QUESTION, USER

AGENT_COLORS = ("cyan", "magenta", "yellow", "blue", "bright_red", "bright_cyan", "bright_magenta")
USER_COLOR = "bright_green"
EVERYONE_COLOR = "white"
QUESTION_COLOR = "bright_yellow"

TASK_MARKERS = {
    "todo": ("○", "white"),
    "in_progress": ("▶", "yellow"),
    "blocked": ("■", "red"),
    "done": ("✓", "green"),
}

GOAL_STATUS_STYLES = {
    "active": "green",
    "paused": "yellow",
    "done": "dim green",
    "cancelled": "dim red",
}


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


def question(item: Message) -> Text:
    goal = f"  goal #{item.goal_id}" if item.goal_id is not None else ""
    header = Text.assemble(
        (f"#{item.id} ", "dim"),
        participant(item.sender),
        (" asks", "dim"),
        ("  " + render.clock(item.created_at) + goal, "dim"),
    )

    return Text.assemble(header, "\n", Text(item.body.strip(), style="bold"))


def event(item: Message) -> Table:
    body = Text(item.body, style="dim")
    body.highlight_words([item.sender], style=participant_color(item.sender))

    table = Table.grid(padding=(0, 1), expand=True)
    table.add_column(no_wrap=True, style="dim")
    table.add_column(no_wrap=True, style="dim")
    table.add_column(ratio=1)
    table.add_row(render.clock(item.created_at), "•", body)

    return table


def presence_style(agent: Agent, now: float) -> str:
    if agent.activity == OFFLINE:
        return "dim"

    if render.is_listening(agent, now):
        return "green"

    return "yellow" if render.is_online(agent, now) else "red"


def agent_row(agent: Agent, now: float, starting: bool = False) -> Text:
    style = "yellow" if starting else presence_style(agent, now)
    role = f" ({agent.role})" if agent.role else ""
    provider = f" · {agent.provider}" if agent.provider else ""
    presence = "starting…" if starting else render.presence(agent, now)

    text = Text.assemble(
        ("● ", style),
        participant(agent.name),
        (role, "dim"),
        ("  ", ""),
        (presence, style),
        (provider, "dim"),
    )

    if agent.status and not starting:
        text.append(f"  · {agent.status}")

    text.no_wrap = True
    text.overflow = "ellipsis"

    return text


def task_cells(task: Task) -> tuple[Text, Text, Text]:
    marker, color = TASK_MARKERS.get(task.status, ("?", "white"))
    title_style = "dim" if task.status == "done" else ""
    assignee_style = participant_color(task.assignee) if task.assignee else "dim"

    return (
        Text(marker, style=color),
        Text.assemble((f"#{task.id} ", "dim"), (task.title, title_style)),
        Text(task.assignee or "unassigned", style=assignee_style),
    )


def task_table(tasks: list[Task]) -> RenderableType:
    if not tasks:
        return Text("  no tasks yet", style="dim")

    table = Table.grid(padding=(0, 1), expand=True)
    table.add_column(width=1)
    table.add_column(ratio=1)
    table.add_column(no_wrap=True, justify="right")

    for task in tasks:
        table.add_row(*task_cells(task))

    return Padding(table, (0, 0, 0, 2))


def goal_block(goal: Goal, tasks: list[Task]) -> Group:
    header = Text.assemble(
        (f"#{goal.id} ", "dim"),
        (goal.title, "bold"),
        ("  ", ""),
        (goal.status, GOAL_STATUS_STYLES.get(goal.status, "")),
    )

    return Group(header, task_table(tasks), Text())


def goal_entry(goal: Goal, tasks: list[Task], selected: bool, unseen: int) -> Text:
    done = sum(task.status == "done" for task in tasks)
    progress = f"  {done}/{len(tasks)}" if tasks else ""

    return Text.assemble(
        ("▸ " if selected else "  ", "bold"),
        (f"#{goal.id} ", "dim"),
        (goal.title, "bold" if selected else ""),
        ("  ", ""),
        (goal.status, GOAL_STATUS_STYLES.get(goal.status, "")),
        (progress, "dim"),
        unseen_badge(unseen),
    )


def general_entry(selected: bool, unseen: int) -> Text:
    return Text.assemble(
        ("▸ " if selected else "  ", "bold"),
        ("general (no goal)", "bold" if selected else "dim"),
        unseen_badge(unseen),
    )


def unseen_badge(unseen: int) -> Text:
    return Text(f"  ● {unseen} new", style=f"bold {USER_COLOR}") if unseen else Text()
