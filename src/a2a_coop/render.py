import time
from typing import Callable, Iterable, TypeVar

from .models import Agent, Goal, Message, Task
from .store import EVENT, OFFLINE, WAITING

T = TypeVar("T")

LISTENING_FRESHNESS_SECONDS = 15


def lines(items: Iterable[T], render_item: Callable[[T], str], empty: str) -> str:
    rendered = [render_item(item) for item in items]

    return "\n".join(rendered) if rendered else empty


def section(title: str, body: str) -> str:
    return f"{title}:\n{indent(body)}"


def indent(text: str, prefix: str = "  ") -> str:
    return "\n".join(prefix + line for line in text.splitlines())


def clock(epoch: float) -> str:
    return time.strftime("%H:%M:%S", time.localtime(epoch))


def elapsed(seconds: float) -> str:
    for unit, size in (("d", 86400), ("h", 3600), ("m", 60)):
        if seconds >= size:
            return f"{int(seconds // size)}{unit}"

    return f"{int(seconds)}s"


def is_listening(agent: Agent, now: float) -> bool:
    return agent.activity == WAITING and now - agent.last_seen < LISTENING_FRESHNESS_SECONDS


def presence(agent: Agent, now: float) -> str:
    if agent.activity == OFFLINE:
        return "offline"

    if is_listening(agent, now):
        return "listening"

    return f"seen {elapsed(now - agent.last_seen)} ago"


def agent_line(agent: Agent, now: float) -> str:
    role = f" ({agent.role})" if agent.role else ""
    status = f" - {agent.status}" if agent.status else ""

    return f"{agent.name}{role} [{presence(agent, now)}]{status}"


def agents(items: Iterable[Agent], now: float) -> str:
    return lines(items, lambda agent: agent_line(agent, now), "No agents have joined yet.")


def goal_line(goal: Goal) -> str:
    return f"Goal #{goal.id} [{goal.status}] {goal.title}"


def goals(items: Iterable[Goal]) -> str:
    return lines(items, goal_line, "No goals.")


def goal_details(goal: Goal, goal_tasks: Iterable[Task]) -> str:
    parts = [goal_line(goal)]

    if goal.description:
        parts.append(indent(goal.description))

    parts.append(indent(section("Tasks", tasks(goal_tasks))))

    return "\n".join(parts)


def task_line(task: Task) -> str:
    return f"Task #{task.id} [{task.status}] {task.title} (goal #{task.goal_id}, {task.assignee or 'unassigned'})"


def task_details(task: Task) -> str:
    parts = [task_line(task)]

    if task.description:
        parts.append(indent(task.description))

    if task.result:
        parts.append(indent(f"Result: {task.result}"))

    return "\n".join(parts)


def tasks(items: Iterable[Task]) -> str:
    return lines(items, task_details, "No tasks.")


def message_line(message: Message) -> str:
    first_line, *more_lines = message.body.splitlines()
    continuation = "".join(f"\n    {line}" for line in more_lines)

    return f"{message_header(message)} {first_line}{continuation}"


def message_header(message: Message) -> str:
    stamp = f"#{message.id} {clock(message.created_at)}"

    if message.kind == EVENT:
        return f"{stamp} *"

    return f"{stamp} {message.sender} -> {message.recipient}:"


def messages(items: Iterable[Message], empty: str = "No messages.") -> str:
    return lines(items, message_line, empty)
