import argparse
import sys
import time
from pathlib import Path
from typing import Optional

from rich.console import Console

from . import connect, events, pretty, render, server, tui
from .errors import CoopError
from .models import Message
from .paths import DB_ENV_VAR, default_db_path
from .store import TASK_STATUSES, USER, CoopStore

WATCH_INTERVAL_SECONDS = 1.0

GOAL_STATUS_VERBS = {
    "pause": "paused",
    "resume": "active",
    "done": "done",
    "cancel": "cancelled",
}


def main(argv: Optional[list[str]] = None) -> None:
    args = build_parser().parse_args(argv)

    if args.command != "serve":
        configure_console()

    try:
        args.handler(CoopStore(args.db), args)
    except CoopError as error:
        sys.exit(f"error: {error}")


def configure_console() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def expanded_path(value: str) -> Path:
    return Path(value).expanduser()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="a2a-coop",
        description="Let AI agents such as Claude and Codex cooperate on goals you give them, over MCP.",
    )
    parser.add_argument(
        "--db",
        type=expanded_path,
        default=default_db_path(),
        help=f"shared coop database (default: %(default)s, overridable with ${DB_ENV_VAR})",
    )
    commands = parser.add_subparsers(dest="command", required=True, metavar="COMMAND")

    add_serve_command(commands)
    add_overview_commands(commands)
    add_goal_commands(commands)
    add_task_commands(commands)
    add_message_commands(commands)
    add_admin_commands(commands)

    return parser


def add_serve_command(commands: argparse._SubParsersAction) -> None:
    serve = commands.add_parser("serve", help="run the MCP server for one agent (used by Claude/Codex, over stdio)")
    serve.add_argument("--agent", required=True, help="name of the connecting agent, e.g. claude or codex")
    serve.add_argument("--role", default="", help="optional role or specialty shown to teammates")
    serve.set_defaults(handler=run_server)


def add_overview_commands(commands: argparse._SubParsersAction) -> None:
    status = commands.add_parser("status", help="overview of agents, open goals and your inbox")
    status.set_defaults(handler=show_status)

    agents = commands.add_parser("agents", help="list connected agents")
    agents.set_defaults(handler=show_agents)


def add_goal_commands(commands: argparse._SubParsersAction) -> None:
    goal = commands.add_parser("goal", help="create and manage goals").add_subparsers(
        dest="goal_command", required=True, metavar="ACTION"
    )

    add = goal.add_parser("add", help="give the agents a new goal")
    add.add_argument("title")
    add.add_argument("-d", "--description", default="")
    add.set_defaults(handler=add_goal)

    listing = goal.add_parser("list", help="list goals")
    listing.add_argument("--all", action="store_true", help="include done and cancelled goals")
    listing.set_defaults(handler=list_goals)

    show = goal.add_parser("show", help="show a goal and its tasks")
    show.add_argument("goal_id", type=int)
    show.set_defaults(handler=show_goal)

    edit = goal.add_parser("set", help="edit a goal's title or description")
    edit.add_argument("goal_id", type=int)
    edit.add_argument("--title")
    edit.add_argument("-d", "--description")
    edit.set_defaults(handler=edit_goal)

    remove = goal.add_parser("remove", aliases=["rm"], help="delete goals together with their tasks")
    remove.add_argument("goal_ids", type=int, nargs="+", metavar="goal_id")
    remove.set_defaults(handler=remove_goals)

    add_goal_status_commands(goal)


def add_goal_status_commands(goal: argparse._SubParsersAction) -> None:
    for verb, status in GOAL_STATUS_VERBS.items():
        command = goal.add_parser(verb, help=f"mark a goal as {status}")
        command.add_argument("goal_id", type=int)
        command.set_defaults(handler=set_goal_status, status=status)


def add_task_commands(commands: argparse._SubParsersAction) -> None:
    task = commands.add_parser("task", help="create and manage tasks").add_subparsers(
        dest="task_command", required=True, metavar="ACTION"
    )

    add = task.add_parser("add", help="add a task to a goal")
    add.add_argument("goal_id", type=int)
    add.add_argument("title")
    add.add_argument("-d", "--description", default="")
    add.add_argument("--to", dest="assignee", help="assign it to an agent")
    add.set_defaults(handler=add_task)

    listing = task.add_parser("list", help="list tasks")
    listing.add_argument("--goal", dest="goal_id", type=int)
    listing.add_argument("--agent", dest="assignee")
    listing.add_argument("--all", action="store_true", help="include done tasks")
    listing.set_defaults(handler=list_tasks)

    update = task.add_parser("set", help="change a task's status, assignee, title, description or result")
    update.add_argument("task_id", type=int)
    update.add_argument("--status", choices=TASK_STATUSES)
    update.add_argument("--title")
    update.add_argument("-d", "--description")
    update.add_argument("--result")
    assignment = update.add_mutually_exclusive_group()
    assignment.add_argument("--to", dest="assignee", help="hand the task to an agent")
    assignment.add_argument("--unassign", action="store_true", help="free the task so anyone can claim it")
    update.set_defaults(handler=update_task)

    remove = task.add_parser("remove", aliases=["rm"], help="delete one or more tasks")
    remove.add_argument("task_ids", type=int, nargs="+", metavar="task_id")
    remove.set_defaults(handler=remove_tasks)


def add_message_commands(commands: argparse._SubParsersAction) -> None:
    send = commands.add_parser("send", help="send a message to an agent, or to 'all'")
    send.add_argument("recipient")
    send.add_argument("text", nargs="+")
    send.set_defaults(handler=send_message)

    inbox = commands.add_parser("inbox", help="show unread messages addressed to you")
    inbox.set_defaults(handler=show_inbox)

    log = commands.add_parser("log", help="show recent coop messages")
    log.add_argument("-n", "--limit", type=int, default=30)
    log.add_argument("--involving", help="only messages sent by or to this participant")
    log.set_defaults(handler=show_log)

    watch = commands.add_parser("watch", help="live dashboard with a message box (Ctrl+Q to quit)")
    watch.add_argument("-n", "--backlog", type=int, default=50, help="how many recent messages to show")
    watch.add_argument("--stream", action="store_true", help="print messages as they arrive instead of the dashboard")
    watch.set_defaults(handler=watch_messages)


def add_admin_commands(commands: argparse._SubParsersAction) -> None:
    setup = commands.add_parser("setup", help="print how to connect Claude Code and Codex")
    setup.add_argument("--claude-name", default="claude")
    setup.add_argument("--codex-name", default="codex")
    setup.set_defaults(handler=show_setup)

    kick = commands.add_parser("kick", help="remove an agent from the coop")
    kick.add_argument("name")
    kick.set_defaults(handler=kick_agent)

    reset = commands.add_parser("reset", help="delete all agents, goals, tasks and messages")
    reset.add_argument("--yes", action="store_true", help="confirm the reset")
    reset.set_defaults(handler=reset_coop)


def run_server(store: CoopStore, args: argparse.Namespace) -> None:
    server.serve(store, args.agent, args.role)


def show_status(store: CoopStore, args: argparse.Namespace) -> None:
    print(render.section("Agents", render.agents(store.list_agents(), time.time())))
    print()
    print(render.section("Open goals", open_goals_overview(store)))
    print()
    print(f"Unread messages for you: {store.count_unread(USER)} (see `a2a-coop inbox`)")


def open_goals_overview(store: CoopStore) -> str:
    goals = store.list_goals()

    if not goals:
        return "No open goals. Add one with `a2a-coop goal add \"...\"`."

    return "\n".join(render.goal_details(goal, store.list_tasks(goal_id=goal.id)) for goal in goals)


def show_agents(store: CoopStore, args: argparse.Namespace) -> None:
    print(render.agents(store.list_agents(), time.time()))


def add_goal(store: CoopStore, args: argparse.Namespace) -> None:
    goal = store.create_goal(args.title, args.description)
    store.announce(USER, events.goal_created(goal))

    print(f"Created {render.goal_line(goal)}")


def list_goals(store: CoopStore, args: argparse.Namespace) -> None:
    print(render.goals(store.list_goals(include_closed=args.all)))


def show_goal(store: CoopStore, args: argparse.Namespace) -> None:
    print(render.goal_details(store.get_goal(args.goal_id), store.list_tasks(goal_id=args.goal_id)))


def set_goal_status(store: CoopStore, args: argparse.Namespace) -> None:
    goal = store.set_goal_status(args.goal_id, args.status)
    store.announce(USER, events.goal_status_changed(goal))

    print(render.goal_line(goal))


def edit_goal(store: CoopStore, args: argparse.Namespace) -> None:
    goal = store.update_goal(args.goal_id, title=args.title, description=args.description)
    store.announce(USER, events.goal_edited(goal))

    print(render.goal_details(goal, store.list_tasks(goal_id=goal.id)))


def remove_goals(store: CoopStore, args: argparse.Namespace) -> None:
    goals = [store.get_goal(goal_id) for goal_id in args.goal_ids]

    for goal in goals:
        removed, tasks = store.remove_goal(goal.id)
        store.announce(USER, events.goal_removed(removed, len(tasks)))

        print(f"Removed {render.goal_line(removed)} and {len(tasks)} task(s)")


def add_task(store: CoopStore, args: argparse.Namespace) -> None:
    task = store.create_task(args.goal_id, args.title, USER, args.description, args.assignee)
    store.announce(USER, events.task_created(USER, task))

    print(render.task_details(task))


def list_tasks(store: CoopStore, args: argparse.Namespace) -> None:
    print(render.tasks(store.list_tasks(args.goal_id, args.assignee, include_done=args.all)))


def update_task(store: CoopStore, args: argparse.Namespace) -> None:
    task = store.update_task(
        args.task_id,
        status=args.status,
        result=args.result,
        assignee=args.assignee,
        title=args.title,
        description=args.description,
        unassign=args.unassign,
    )
    store.announce(USER, events.task_updated(USER, task))

    print(render.task_details(task))


def remove_tasks(store: CoopStore, args: argparse.Namespace) -> None:
    tasks = [store.get_task(task_id) for task_id in args.task_ids]

    for task in tasks:
        store.remove_task(task.id)
        store.announce(USER, events.task_removed(USER, task))

        print(f"Removed {render.task_line(task)}")


def send_message(store: CoopStore, args: argparse.Namespace) -> None:
    message = store.send_message(USER, args.recipient, " ".join(args.text))

    print_cards([message], "")


def show_inbox(store: CoopStore, args: argparse.Namespace) -> None:
    print_cards(store.take_unread(USER), "No unread messages.")


def show_log(store: CoopStore, args: argparse.Namespace) -> None:
    print_cards(store.recent_messages(args.limit, args.involving), "No messages.")


def print_cards(messages: list[Message], empty: str) -> None:
    console = Console()

    if not messages:
        console.print(empty, style="dim")

    for message in messages:
        console.print(pretty.message(message))


def watch_messages(store: CoopStore, args: argparse.Namespace) -> None:
    if args.stream or not sys.stdout.isatty():
        stream_messages(store, args.backlog)
    else:
        tui.watch(store, args.backlog)


def stream_messages(store: CoopStore, backlog: int) -> None:
    console = Console()
    recent = store.recent_messages(backlog) if backlog > 0 else []
    last_id = print_new_cards(console, recent, store.latest_message_id())

    try:
        follow_messages(console, store, last_id)
    except KeyboardInterrupt:
        pass


def follow_messages(console: Console, store: CoopStore, last_id: int) -> None:
    while True:
        last_id = print_new_cards(console, store.messages_after(last_id), last_id)
        time.sleep(WATCH_INTERVAL_SECONDS)


def print_new_cards(console: Console, messages: list[Message], last_id: int) -> int:
    for message in messages:
        console.print(pretty.message(message))

    return messages[-1].id if messages else last_id


def show_setup(store: CoopStore, args: argparse.Namespace) -> None:
    print(connect.setup_text(args.db, args.claude_name, args.codex_name))


def kick_agent(store: CoopStore, args: argparse.Namespace) -> None:
    store.remove_agent(args.name)

    print(f"Removed {args.name}.")


def reset_coop(store: CoopStore, args: argparse.Namespace) -> None:
    if not args.yes:
        sys.exit("Refusing to reset without --yes. This deletes all agents, goals, tasks and messages.")

    store.reset()

    print(f"Reset {store.path}.")

