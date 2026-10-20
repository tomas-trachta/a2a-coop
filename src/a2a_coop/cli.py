import argparse
import shutil
import sys
import time
from pathlib import Path
from typing import Optional

from rich.console import Console

from . import connect, events, launch, preferences, pretty, projects, providers, render, server
from .errors import CoopError
from .models import Message
from .paths import DB_ENV_VAR, default_db_path
from .store import TASK_STATUSES, USER, CoopStore

PROGRAM = "a2a-coop"
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
        choose_coop(args)
        args.handler(CoopStore(args.db), args)
    except CoopError as error:
        exit_with_error(error, getattr(args, "hold", False))


def choose_coop(args: argparse.Namespace) -> None:
    args.home = (args.db or default_db_path()).parent
    args.chosen = args.db is not None or args.project is not None

    if args.project:
        args.db = projects.get_project(args.home, args.project).db
    elif args.db is None:
        args.db = default_db_path()


def exit_with_error(error: CoopError, hold: bool) -> None:
    print(f"error: {error}", file=sys.stderr)

    if hold:
        input("Press Enter to close this window.")

    sys.exit(1)


def configure_console() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def expanded_path(value: str) -> Path:
    return Path(value).expanduser()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=PROGRAM,
        description="Let AI agents such as Claude and Codex cooperate on goals you give them, over MCP. "
        "Run without a command to open the dashboard.",
    )
    parser.add_argument(
        "--db",
        type=expanded_path,
        help=f"shared coop database (default: {default_db_path()}, overridable with ${DB_ENV_VAR})",
    )
    parser.add_argument("--project", "-P", help="work in this project instead (see `a2a-coop project list`)")
    parser.set_defaults(handler=watch_messages, backlog=50, stream=False, command=None)
    commands = parser.add_subparsers(dest="command", metavar="COMMAND")

    add_serve_command(commands)
    add_overview_commands(commands)
    add_project_commands(commands)
    add_team_commands(commands)
    add_agent_commands(commands)
    add_goal_commands(commands)
    add_task_commands(commands)
    add_message_commands(commands)
    add_admin_commands(commands)

    return parser


def add_serve_command(commands: argparse._SubParsersAction) -> None:
    serve = commands.add_parser("serve", help="run the MCP server for one agent (used by Claude/Codex, over stdio)")
    serve.add_argument("--agent", required=True, help="name of the connecting agent, e.g. claude or codex")
    serve.add_argument("--role", default="", help="role shown to teammates (default: keep the stored role)")
    serve.set_defaults(handler=run_server)


def add_overview_commands(commands: argparse._SubParsersAction) -> None:
    status = commands.add_parser("status", help="overview of agents, open goals and your inbox")
    status.set_defaults(handler=show_status)

    agents = commands.add_parser("agents", help="list agents (same as `agent list`)")
    agents.set_defaults(handler=show_agents)


def add_project_commands(commands: argparse._SubParsersAction) -> None:
    project = commands.add_parser("project", help="create and list projects, each with its own team and goals").add_subparsers(
        dest="project_command", metavar="ACTION", required=True
    )

    add = project.add_parser("add", help="create a project with its own team, goals and conversation")
    add.add_argument("name")
    add.add_argument("--dir", dest="folder", default="", help="folder its agents start in by default")
    add.set_defaults(handler=add_project)

    listing = project.add_parser("list", help="list projects")
    listing.set_defaults(handler=list_projects)


def add_team_commands(commands: argparse._SubParsersAction) -> None:
    team = commands.add_parser("team", help="create, list and remove the teams of a project").add_subparsers(
        dest="team_command", metavar="ACTION", required=True
    )

    add = team.add_parser("add", help="create a team that works on the project's goals with its own agents")
    add.add_argument("name")
    add.add_argument("--empty", action="store_true", help="do not add a Claude and a Codex agent to it")
    add.set_defaults(handler=add_team)

    listing = team.add_parser("list", help="list teams with their agents")
    listing.set_defaults(handler=list_teams)

    remove = team.add_parser("remove", aliases=["rm"], help="remove a team together with its agents")
    remove.add_argument("name")
    remove.set_defaults(handler=remove_team)


def add_agent_commands(commands: argparse._SubParsersAction) -> None:
    agent = commands.add_parser("agent", help="create, start and manage agents").add_subparsers(
        dest="agent_command", required=True, metavar="ACTION"
    )

    add = agent.add_parser("add", help="define a new agent, e.g. a second Claude with another role")
    add.add_argument("name", nargs="?", help="agent name (default: derived from provider and role)")
    add.add_argument("--provider", "-p", choices=list(providers.PROVIDERS), default="claude")
    add.add_argument("--role", "-r", default="", help='what it does, e.g. "code reviewer"')
    add.add_argument("--dir", dest="workdir", default="", help="working directory (default: where you start it)")
    add.add_argument("--team", "-t", default="", help="team it joins (default: the project's first team)")
    add.add_argument("--start", action="store_true", help="start it in a new terminal right away")
    add.set_defaults(handler=add_agent)

    listing = agent.add_parser("list", help="list agents")
    listing.set_defaults(handler=show_agents)

    edit = agent.add_parser("set", help="change an agent's role, provider, working directory or team")
    edit.add_argument("name")
    edit.add_argument("--provider", "-p", choices=list(providers.PROVIDERS))
    edit.add_argument("--role", "-r")
    edit.add_argument("--dir", dest="workdir")
    edit.add_argument("--team", "-t", help="move it to another team")
    edit.set_defaults(handler=edit_agent)

    start = agent.add_parser("start", help="start an agent in a new terminal window (or here with --here)")
    start.add_argument("name")
    start.add_argument("--here", action="store_true", help="run it in this terminal")
    start.add_argument("--dir", dest="workdir", type=expanded_path, help=argparse.SUPPRESS)
    start.add_argument("--hold", action="store_true", help=argparse.SUPPRESS)
    start.set_defaults(handler=start_agent)

    remove = agent.add_parser("remove", aliases=["rm"], help="remove an agent from the coop")
    remove.add_argument("name")
    remove.set_defaults(handler=kick_agent)


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
    send.add_argument("--goal", dest="goal_id", type=int, help="file the message under this goal's conversation")
    send.set_defaults(handler=send_message)

    inbox = commands.add_parser("inbox", help="show unread messages addressed to you")
    inbox.set_defaults(handler=show_inbox)

    questions = commands.add_parser("questions", help="open questions the agents asked you")
    questions.set_defaults(handler=show_questions)

    answer = commands.add_parser("answer", help="answer a question by its number")
    answer.add_argument("message_id", type=int)
    answer.add_argument("text", nargs="+")
    answer.set_defaults(handler=answer_question)

    dismiss = commands.add_parser("dismiss", help="close questions without answering them")
    dismiss.add_argument("message_ids", type=int, nargs="+", metavar="message_id")
    dismiss.set_defaults(handler=dismiss_questions)

    log = commands.add_parser("log", help="show recent coop messages")
    log.add_argument("-n", "--limit", type=int, default=30)
    log.add_argument("--involving", help="only messages sent by or to this participant")
    log.add_argument("--goal", dest="goal_id", type=int, help="only the conversation of this goal")
    log.set_defaults(handler=show_log)

    watch = commands.add_parser("watch", help="open the dashboard window (or follow messages here with --stream)")
    watch.add_argument("-n", "--backlog", type=int, default=50, help="how many recent messages to show")
    watch.add_argument("--stream", action="store_true", help="print messages as they arrive instead of opening a window")
    watch.set_defaults(handler=watch_messages)


def add_admin_commands(commands: argparse._SubParsersAction) -> None:
    setup = commands.add_parser("setup", help="connect the installed Claude Code / Codex to the coop")
    setup.add_argument("--claude-name", default="claude")
    setup.add_argument("--codex-name", default="codex")
    setup.add_argument("--print", action="store_true", help="only print the configuration, change nothing")
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
    print(render.section("Teams", teams_overview(store)))
    print()
    print(render.section("Open goals", open_goals_overview(store)))
    print()
    print(f"Unread messages for you: {store.count_unread(USER)} (see `a2a-coop inbox`)")
    print(f"Open questions for you: {len(store.open_questions())} (see `a2a-coop questions`)")


def open_goals_overview(store: CoopStore) -> str:
    goals = store.list_goals()

    if not goals:
        return "No open goals. Add one with `a2a-coop goal add \"...\"`."

    return "\n".join(render.goal_details(goal, store.list_tasks(goal_id=goal.id)) for goal in goals)


def add_project(store: CoopStore, args: argparse.Namespace) -> None:
    project = projects.add_project(args.home, args.name, providers.normalize_workdir(args.folder))
    added = launch.ensure_default_agents(CoopStore(project.db))

    print(f"Created project {project.name}" + (f" with agents {', '.join(agent.name for agent in added)}." if added else "."))
    print(f"Open it with `{PROGRAM} --project {connect.shell_join([project.name])}` or pick it in the dashboard.")


def list_projects(store: CoopStore, args: argparse.Namespace) -> None:
    for project in projects.list_projects(args.home):
        team = ", ".join(agent.name for agent in CoopStore(project.db).list_agents()) if project.db.exists() else ""
        folder = f"  ({project.folder})" if project.folder else ""

        print(f"{project.name}{folder}: {team or 'no agents yet'}")


def add_team(store: CoopStore, args: argparse.Namespace) -> None:
    team = store.create_team(args.name)
    added = [] if args.empty else launch.add_team_agents(store, team)

    print(f"Created team {team}" + (f" with agents {', '.join(agent.name for agent in added)}." if added else "."))


def list_teams(store: CoopStore, args: argparse.Namespace) -> None:
    for team in store.list_teams():
        members = ", ".join(agent.name for agent in store.list_agents(team))

        print(f"{team}: {members or 'no agents yet'}")


def remove_team(store: CoopStore, args: argparse.Namespace) -> None:
    team = store.get_team(args.name)
    removed = store.remove_team(team)

    print(f"Removed team {team}" + (f" and its agents {', '.join(agent.name for agent in removed)}." if removed else "."))


def show_agents(store: CoopStore, args: argparse.Namespace) -> None:
    print(teams_overview(store))


def teams_overview(store: CoopStore) -> str:
    now = time.time()

    return "\n".join(render.section(team, render.agents(store.list_agents(team), now)) for team in store.list_teams())


def add_agent(store: CoopStore, args: argparse.Namespace) -> None:
    taken = {agent.name for agent in store.list_agents()}
    name = args.name or providers.suggested_name(args.provider, args.role, taken)
    agent = store.define_agent(name, args.provider, args.role, providers.normalize_workdir(args.workdir), args.team)

    print(f"Added {render.agent_line(agent, time.time())}")

    if args.start:
        print(f"Started {agent.name} in {launch.start_in_window(store.path, agent, Path.cwd())}.")
    else:
        print(f"Start it with `a2a-coop agent start {agent.name}` or from the dashboard.")


def edit_agent(store: CoopStore, args: argparse.Namespace) -> None:
    workdir = providers.normalize_workdir(args.workdir) if args.workdir is not None else None
    agent = store.update_agent(args.name, role=args.role, provider=args.provider, workdir=workdir, team=args.team)

    print(render.agent_line(agent, time.time()))


def start_agent(store: CoopStore, args: argparse.Namespace) -> None:
    agent = store.get_agent(args.name)
    fallback = args.workdir or Path.cwd()

    if args.here:
        sys.exit(launch.run_here(store.path, agent, fallback))

    print(f"Started {agent.name} in {launch.start_in_window(store.path, agent, fallback)}.")


def add_goal(store: CoopStore, args: argparse.Namespace) -> None:
    goal = store.create_goal(args.title, args.description)
    store.announce(USER, events.goal_created(goal), goal.id)

    print(f"Created {render.goal_line(goal)}")


def list_goals(store: CoopStore, args: argparse.Namespace) -> None:
    print(render.goals(store.list_goals(include_closed=args.all)))


def show_goal(store: CoopStore, args: argparse.Namespace) -> None:
    print(render.goal_details(store.get_goal(args.goal_id), store.list_tasks(goal_id=args.goal_id)))


def set_goal_status(store: CoopStore, args: argparse.Namespace) -> None:
    goal = store.set_goal_status(args.goal_id, args.status)
    store.announce(USER, events.goal_status_changed(goal), goal.id)

    print(render.goal_line(goal))


def edit_goal(store: CoopStore, args: argparse.Namespace) -> None:
    goal = store.update_goal(args.goal_id, title=args.title, description=args.description)
    store.announce(USER, events.goal_edited(goal), goal.id)

    print(render.goal_details(goal, store.list_tasks(goal_id=goal.id)))


def remove_goals(store: CoopStore, args: argparse.Namespace) -> None:
    goals = [store.get_goal(goal_id) for goal_id in args.goal_ids]

    for goal in goals:
        removed, tasks = store.remove_goal(goal.id)
        store.announce(USER, events.goal_removed(removed, len(tasks)))

        print(f"Removed {render.goal_line(removed)} and {len(tasks)} task(s)")


def add_task(store: CoopStore, args: argparse.Namespace) -> None:
    task = store.create_task(args.goal_id, args.title, USER, args.description, args.assignee)
    store.announce(USER, events.task_created(USER, task), task.goal_id)

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
    store.announce(USER, events.task_updated(USER, task), task.goal_id)

    print(render.task_details(task))


def remove_tasks(store: CoopStore, args: argparse.Namespace) -> None:
    tasks = [store.get_task(task_id) for task_id in args.task_ids]

    for task in tasks:
        store.remove_task(task.id)
        store.announce(USER, events.task_removed(USER, task), task.goal_id)

        print(f"Removed {render.task_line(task)}")


def send_message(store: CoopStore, args: argparse.Namespace) -> None:
    message = store.send_message(USER, args.recipient, " ".join(args.text), goal_id=args.goal_id)

    print_cards([message], "")


def show_inbox(store: CoopStore, args: argparse.Namespace) -> None:
    print_cards(store.take_unread(USER), "No unread messages.")


def show_questions(store: CoopStore, args: argparse.Namespace) -> None:
    print_cards(store.open_questions(), "No open questions.")


def answer_question(store: CoopStore, args: argparse.Namespace) -> None:
    print_cards([store.answer_question(args.message_id, " ".join(args.text))], "")


def dismiss_questions(store: CoopStore, args: argparse.Namespace) -> None:
    for message_id in args.message_ids:
        store.dismiss_question(message_id)

        print(f"Dismissed #{message_id}.")


def show_log(store: CoopStore, args: argparse.Namespace) -> None:
    if args.goal_id is not None:
        store.get_goal(args.goal_id)
        print_cards(store.goal_messages(args.goal_id, args.limit), "No messages for this goal.")
    else:
        print_cards(store.recent_messages(args.limit, args.involving), "No messages.")


def print_cards(messages: list[Message], empty: str) -> None:
    console = Console()

    if not messages:
        console.print(empty, style="dim")

    for message in messages:
        console.print(pretty.message(message))


def watch_messages(store: CoopStore, args: argparse.Namespace) -> None:
    if args.stream:
        stream_messages(store, args.backlog)
        return

    store = last_project_store(args) or store
    launch.ensure_default_agents(store)

    try:
        open_dashboard(store, args.backlog, args.home)
    except CoopError as error:
        print(f"{error} Following messages here instead.", file=sys.stderr)
        stream_messages(store, args.backlog)


def last_project_store(args: argparse.Namespace) -> Optional[CoopStore]:
    if args.chosen:
        return None

    name = preferences.load_project(preferences.preferences_path(args.home / projects.DB_FILE))
    project = projects.find_project(args.home, name) if name else None

    return CoopStore(project.db) if project is not None else None


def open_dashboard(store: CoopStore, backlog: int, home: Path) -> None:
    try:
        from . import gui
    except ImportError as error:
        raise CoopError(f"The dashboard needs tkinter ({error}).") from error

    gui.watch(store, backlog, home)


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
    if args.print:
        print(connect.setup_text(args.db, args.claude_name, args.codex_name))
        return

    for line in connect.configure_clients(args.db, args.claude_name, args.codex_name):
        print(line)

    for agent in launch.ensure_default_agents(store):
        print(f"Added agent {agent.name} ({agent.provider}).")

    print()
    print(f"Open the dashboard with `{dashboard_command()}` and start agents from there (double-click one).")

    if not shutil.which(PROGRAM):
        print(f"Add {installed_scripts_dir()} to your PATH to run `{PROGRAM}` from anywhere.")


def dashboard_command() -> str:
    if shutil.which(PROGRAM):
        return PROGRAM

    return shortest_path(installed_scripts_dir() / PROGRAM).as_posix()


def installed_scripts_dir() -> Path:
    return Path(sys.executable).parent


def shortest_path(path: Path) -> Path:
    try:
        return path.relative_to(Path.cwd())
    except ValueError:
        return path


def kick_agent(store: CoopStore, args: argparse.Namespace) -> None:
    store.remove_agent(args.name)

    print(f"Removed {args.name}.")


def reset_coop(store: CoopStore, args: argparse.Namespace) -> None:
    if not args.yes:
        sys.exit("Refusing to reset without --yes. This deletes all agents, goals, tasks and messages.")

    store.reset()

    print(f"Reset {store.path}.")

