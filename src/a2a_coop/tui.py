import time
from pathlib import Path
from typing import Iterable, Optional

from rich.console import Group, RenderableType
from rich.text import Text
from textual import events
from textual.app import App, ComposeResult, SystemCommand
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.suggester import SuggestFromList
from textual.widgets import Footer, Input, OptionList, Static
from textual.widgets.option_list import Option

from . import events as coop_events
from . import launch, pretty, providers, render
from .errors import CoopError
from .models import Agent, Goal, Message, Task
from .screens import AgentDraft, AgentForm, GoalDraft, GoalForm, GoalPicker
from .store import EVERYONE, OFFLINE, USER, CoopStore

REFRESH_SECONDS = 1.0
SIDEBAR_MIN_TERMINAL_WIDTH = 100
STARTING_GRACE_SECONDS = 90
NEW_AGENT_OPTION = "+new-agent"

COMPOSER_HINT = "Message everyone, or start with @agent to message one agent  ·  Enter to send"
ANSWER_HINT = "Nothing to answer"
EMPTY_CONVERSATION_HINT = "Nothing said about this goal yet."
NO_GOALS_HINT = "No goals yet. Press Ctrl+G to give the agents one, then start them from the team list."
GENERAL_OPTION = "general"
NO_QUESTIONS_HINT = "No open questions. When an agent asks you something, it is pinned here."

GOAL_ACTIONS = (
    ("pause", "paused", ("active",)),
    ("resume", "active", ("paused",)),
    ("mark done", "done", ("active", "paused")),
    ("cancel", "cancelled", ("active", "paused")),
)

CSS = """
#team {
    height: auto;
    max-height: 10;
    border: round gray;
    border-title-align: left;
    border-subtitle-align: right;
    padding: 0 1;
}

#main {
    height: 1fr;
}

#conversation {
    width: 2fr;
    border: round gray;
    border-title-align: left;
    padding: 0 1;
}

#side {
    width: 1fr;
}

#questions-panel {
    height: auto;
    max-height: 60%;
    border: round gray;
    border-title-align: left;
    border-subtitle-align: right;
    padding: 0 1;
}

#questions-panel.waiting {
    border: heavy $warning;
    border-title-color: $warning;
    border-title-style: bold;
}

#questions {
    height: auto;
    max-height: 20;
    border: none;
    padding: 0;
}

#no-questions {
    color: gray;
}

#sidebar {
    height: 1fr;
    border: round gray;
    border-title-align: left;
    border-subtitle-align: right;
    padding: 0 1;
}

#goal-list {
    height: auto;
    max-height: 12;
    border: none;
    padding: 0;
}

#goal-details {
    height: 1fr;
    margin-top: 1;
}

.message {
    height: auto;
}

.empty-hint {
    color: gray;
}
"""


class QuestionList(OptionList):
    BINDINGS = [Binding("d,delete", "app.dismiss_question", "Dismiss")]


class CoopDashboard(App):
    TITLE = "a2a-coop"
    CSS = CSS

    BINDINGS = [
        Binding("ctrl+o", "pick_goal", "Switch goal", priority=True),
        Binding("ctrl+g", "new_goal", "New goal", priority=True),
        Binding("ctrl+n", "new_agent", "New agent", priority=True),
        Binding("ctrl+t", "focus_team", "Start agents", priority=True),
        Binding("ctrl+r", "focus_answer", "Answer", priority=True),
        Binding("escape", "focus_composer", "Back", show=False),
        Binding("ctrl+q", "quit", "Quit"),
        Binding("pageup", "scroll_conversation(-1)", "Scroll up", show=False),
        Binding("pagedown", "scroll_conversation(1)", "Scroll down", show=False),
    ]

    def __init__(self, store: CoopStore, backlog: int, workdir: Optional[Path] = None):
        super().__init__()
        self.store = store
        self.backlog = backlog
        self.workdir = workdir or Path.cwd()
        self.last_message_id = 0
        self.known_agents: tuple[str, ...] = ()
        self.agents: list[Agent] = []
        self.question_ids: Optional[tuple[int, ...]] = None
        self.questions: list[Message] = []
        self.starting: dict[str, float] = {}
        self.wide = True
        self.goal_id: Optional[int] = None
        self.unseen: dict[Optional[int], int] = {}
        self.details_key: Optional[tuple] = None

    def compose(self) -> ComposeResult:
        yield OptionList(id="team")

        with Horizontal(id="main"):
            yield VerticalScroll(id="conversation")

            with Vertical(id="side"):
                with Vertical(id="questions-panel"):
                    yield Static(NO_QUESTIONS_HINT, id="no-questions")
                    yield QuestionList(id="questions")
                    yield Input(placeholder=ANSWER_HINT, id="answer", disabled=True)

                with Vertical(id="sidebar"):
                    yield OptionList(id="goal-list")

                    with VerticalScroll(id="goal-details"):
                        yield Static(id="goals")

        yield Input(placeholder=COMPOSER_HINT, id="composer")
        yield Footer()

    def on_mount(self) -> None:
        self.label_panels()
        self.query_one("#conversation", VerticalScroll).anchor()

        self.goal_id = latest_goal_id(self.store)
        self.load_conversation()
        self.refresh_dashboard()
        self.set_interval(REFRESH_SECONDS, self.refresh_dashboard)

        self.query_one("#composer", Input).focus()

    def on_resize(self, event: events.Resize) -> None:
        self.wide = event.size.width >= SIDEBAR_MIN_TERMINAL_WIDTH
        self.update_layout()

    def update_layout(self) -> None:
        has_questions = bool(self.question_ids)

        self.query_one("#sidebar").display = self.wide
        self.query_one("#side").display = self.wide or has_questions

    def label_panels(self) -> None:
        self.query_one("#team").border_title = "a2a-coop · team  (Enter on an agent starts it)"
        self.query_one("#questions-panel").border_title = "questions for you"
        self.query_one("#sidebar").border_title = "goals"
        self.query_one("#sidebar").border_subtitle = "Enter opens · ^O all"

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "answer":
            self.answer(event.input)
        elif event.input.id == "composer":
            self.compose_message(event.input)

    def compose_message(self, composer: Input) -> None:
        recipient, body = parse_composer(composer.value)

        if not body:
            self.notify("Type a message after the @name.", severity="warning")
            return

        if self.attempt(lambda: self.store.send_message(USER, recipient, body, goal_id=self.goal_id)):
            composer.clear()
            self.refresh_dashboard()

    def answer(self, answer_box: Input) -> None:
        target = self.selected_question()
        text = answer_box.value.strip()

        if target is None or not text:
            return

        if self.attempt(lambda: self.store.answer_question(target, text)):
            answer_box.clear()
            self.refresh_dashboard()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        if event.option_list.id == "team":
            self.team_option_selected(event.option.id)
        elif event.option_list.id == "goal-list":
            self.open_goal(parse_goal_option(event.option.id))
        elif event.option_list.id == "questions":
            self.query_one("#answer", Input).focus()

    def on_option_list_option_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        if event.option_list.id == "questions":
            self.update_answer_hint()

    def team_option_selected(self, option_id: Optional[str]) -> None:
        if option_id == NEW_AGENT_OPTION:
            self.action_new_agent()
        elif option_id:
            self.start_agent(option_id)

    def action_scroll_conversation(self, direction: int) -> None:
        conversation = self.query_one("#conversation", VerticalScroll)

        if direction < 0:
            conversation.scroll_page_up()
        else:
            conversation.scroll_page_down()

    def action_focus_composer(self) -> None:
        self.query_one("#composer", Input).focus()

    def action_focus_team(self) -> None:
        self.query_one("#team", OptionList).focus()

    def action_focus_answer(self) -> None:
        if not self.question_ids:
            self.notify("No questions are waiting for you.")
            return

        self.query_one("#answer", Input).focus()

    def action_dismiss_question(self) -> None:
        target = self.selected_question()

        if target is not None and self.attempt(lambda: self.store.dismiss_question(target)):
            self.refresh_dashboard()

    def action_pick_goal(self) -> None:
        if isinstance(self.screen, (GoalForm, AgentForm, GoalPicker)):
            return

        goals = self.store.list_goals(include_closed=True)
        options = [self.goal_option(goal) for goal in reversed(goals)] + [self.general_option()]

        self.push_screen(GoalPicker(options, goal_option_id(self.goal_id)), self.picked_goal)

    def picked_goal(self, option_id: Optional[str]) -> None:
        if option_id is not None:
            self.open_goal(parse_goal_option(option_id))

    def open_goal(self, goal_id: Optional[int]) -> None:
        self.goal_id = goal_id
        self.unseen.pop(goal_id, None)
        self.load_conversation()
        self.refresh_dashboard()

    def action_new_goal(self) -> None:
        if not isinstance(self.screen, (GoalForm, AgentForm)):
            self.push_screen(GoalForm(self.create_goal))

    def action_new_agent(self) -> None:
        if not isinstance(self.screen, (GoalForm, AgentForm)):
            taken = {agent.name for agent in self.agents}
            self.push_screen(AgentForm(self.create_agent, taken, self.workdir))

    def create_goal(self, draft: GoalDraft) -> bool:
        created: list[int] = []

        def create() -> None:
            goal = self.store.create_goal(draft.title, draft.description)
            self.store.announce(USER, coop_events.goal_created(goal), goal.id)
            created.append(goal.id)

        if not self.attempt(create):
            return False

        self.open_goal(created[0])

        return True

    def create_agent(self, draft: AgentDraft) -> bool:
        def define() -> None:
            workdir = providers.normalize_workdir(draft.workdir)
            self.store.define_agent(draft.name, draft.provider, draft.role, workdir)

        if not self.attempt(define):
            return False

        self.notify(f"Added agent {draft.name}.")
        self.refresh_dashboard()

        if draft.start:
            self.call_after_refresh(self.start_agent, draft.name)

        return True

    def start_agent(self, name: str, force: bool = False) -> None:
        try:
            agent = self.store.get_agent(name)

            if not force and render.is_online(agent, time.time()):
                self.notify(f"{name} is already running. Use the command palette (Ctrl+P) to start another copy.")
                return

            where = launch.start_in_window(self.store.path, agent, self.workdir)
        except CoopError as error:
            self.notify(str(error), severity="error", timeout=10)
            return

        self.starting[name] = time.time()
        self.notify(f"Starting {name} in {where}.")
        self.refresh_dashboard()

    def set_goal_status(self, goal_id: int, status: str) -> None:
        def change() -> None:
            goal = self.store.set_goal_status(goal_id, status)
            self.store.announce(USER, coop_events.goal_status_changed(goal), goal.id)

        if self.attempt(change):
            self.refresh_dashboard()

    def remove_agent(self, name: str) -> None:
        if self.attempt(lambda: self.store.remove_agent(name)):
            self.notify(f"Removed {name}.")
            self.refresh_dashboard()

    def attempt(self, action) -> bool:
        try:
            action()
        except CoopError as error:
            self.notify(str(error), severity="error")
            return False

        return True

    def get_system_commands(self, screen: Screen) -> Iterable[SystemCommand]:
        yield from super().get_system_commands(screen)
        yield SystemCommand("New goal", "Give the agents a new goal", self.action_new_goal)
        yield SystemCommand("New agent", "Create an agent with its own provider and role", self.action_new_agent)

        for agent in self.agents:
            yield from agent_commands(self, agent)

        for goal in reversed(self.store.list_goals(include_closed=True)):
            yield SystemCommand(
                f"Open goal #{goal.id}: {goal.title}",
                f"Show the conversation of this {goal.status} goal",
                lambda goal_id=goal.id: self.open_goal(goal_id),
            )

        yield SystemCommand("Open general conversation", "Messages that belong to no goal", lambda: self.open_goal(None))

        for goal in self.store.list_goals():
            for label, status, allowed in GOAL_ACTIONS:
                if goal.status in allowed:
                    yield SystemCommand(
                        f"Goal #{goal.id}: {label}",
                        goal.title,
                        lambda goal_id=goal.id, status=status: self.set_goal_status(goal_id, status),
                    )

    def load_conversation(self) -> None:
        conversation = self.query_one("#conversation", VerticalScroll)
        conversation.remove_children()
        conversation.mount(Static(self.empty_hint(), classes="empty-hint"))

        self.last_message_id = self.store.latest_message_id()
        recent = self.store.goal_messages(self.goal_id, self.backlog) if self.backlog > 0 else []

        self.show_messages(recent)
        self.label_conversation()

    def empty_hint(self) -> str:
        if self.goal_id is None and not self.store.list_goals(include_closed=True):
            return NO_GOALS_HINT

        return EMPTY_CONVERSATION_HINT

    def label_conversation(self) -> None:
        conversation = self.query_one("#conversation")
        composer = self.query_one("#composer", Input)

        if self.goal_id is None:
            conversation.border_title = "general conversation (no goal)"
            composer.placeholder = COMPOSER_HINT
            return

        goal = self.store.get_goal(self.goal_id)
        conversation.border_title = f"goal #{goal.id} · {goal.title} · {goal.status}"
        composer.placeholder = f"Message everyone about goal #{goal.id}, or start with @agent  ·  Enter to send"

    def refresh_dashboard(self) -> None:
        self.receive(self.store.messages_after(self.last_message_id))
        self.store.take_unread(USER)

        self.agents = self.store.list_agents()

        self.show_team(self.agents)
        self.update_suggestions(self.agents)
        self.show_questions(self.store.open_questions())
        self.show_goal_list()
        self.show_goals()

    def receive(self, messages: list[Message]) -> None:
        if not messages:
            return

        self.last_message_id = max(self.last_message_id, messages[-1].id)
        self.show_messages([message for message in messages if message.goal_id == self.goal_id])

        for message in messages:
            if message.goal_id != self.goal_id and message.sender != USER:
                self.unseen[message.goal_id] = self.unseen.get(message.goal_id, 0) + 1

        if self.goal_id is not None and any(message.goal_id == self.goal_id for message in messages):
            self.label_conversation()

    def show_messages(self, messages: list[Message]) -> None:
        if not messages:
            return

        self.remove_empty_hint()
        self.query_one("#conversation").mount_all(Static(pretty.message(item), classes="message") for item in messages)

    def remove_empty_hint(self) -> None:
        for hint in self.query(".empty-hint"):
            hint.remove()

    def show_team(self, agents: list[Agent]) -> None:
        now = time.time()
        team = self.query_one("#team", OptionList)

        self.forget_started_agents(agents, now)
        options = [Option(self.agent_prompt(agent, now), id=agent.name) for agent in agents]
        options.append(Option(Text("+ add an agent (Ctrl+N)", style="dim"), id=NEW_AGENT_OPTION))

        sync_options(team, options)
        team.border_subtitle = time.strftime("%H:%M:%S", time.localtime(now))

    def agent_prompt(self, agent: Agent, now: float) -> Text:
        return pretty.agent_row(agent, now, starting=agent.name in self.starting)

    def forget_started_agents(self, agents: list[Agent], now: float) -> None:
        for agent in agents:
            started = self.starting.get(agent.name)

            if started is None:
                continue

            joined = agent.activity != OFFLINE and agent.last_seen >= started
            if joined or now - started > STARTING_GRACE_SECONDS:
                del self.starting[agent.name]

    def update_suggestions(self, agents: list[Agent]) -> None:
        names = tuple(agent.name for agent in agents)

        if names == self.known_agents:
            return

        self.known_agents = names
        mentions = [f"@{name} " for name in names]
        self.query_one("#composer", Input).suggester = SuggestFromList(mentions, case_sensitive=False)

    def show_questions(self, questions: list[Message]) -> None:
        ids = tuple(question.id for question in questions)

        if ids == self.question_ids:
            return

        self.announce_new_questions(questions)
        self.question_ids = ids
        self.questions = questions

        listing = self.query_one("#questions", OptionList)
        sync_options(listing, [Option(pretty.question(question), id=str(question.id)) for question in questions])

        panel = self.query_one("#questions-panel")
        panel.set_class(bool(questions), "waiting")
        panel.border_title = f"questions for you ({len(questions)})" if questions else "questions for you"
        panel.border_subtitle = "↑↓ pick · d dismiss" if len(questions) > 1 else ("d dismiss" if questions else "")
        listing.display = bool(questions)
        self.query_one("#no-questions").display = not questions
        self.query_one("#answer", Input).disabled = not questions

        self.update_answer_hint()
        self.update_layout()

    def announce_new_questions(self, questions: list[Message]) -> None:
        if self.question_ids is None:
            return

        for question in questions:
            if question.id not in self.question_ids:
                self.bell()
                self.notify(first_line(question.body), title=f"{question.sender} asks you", timeout=10)

    def selected_question(self) -> Optional[int]:
        listing = self.query_one("#questions", OptionList)

        if listing.option_count == 0:
            return None

        option = listing.highlighted_option or listing.get_option_at_index(0)

        return int(option.id)

    def update_answer_hint(self) -> None:
        target = self.selected_question()
        answer_box = self.query_one("#answer", Input)

        if target is None:
            answer_box.placeholder = ANSWER_HINT
            return

        sender = next((question.sender for question in self.questions if question.id == target), "")
        answer_box.placeholder = f"Answer #{target} ({sender}), Enter sends"

    def show_goal_list(self) -> None:
        listing = self.query_one("#goal-list", OptionList)
        goals = [goal for goal in self.store.list_goals(include_closed=True) if goal.status in ("active", "paused") or goal.id == self.goal_id]
        options = [*(self.goal_option(goal) for goal in reversed(goals)), self.general_option()]

        sync_options(listing, options, fallback=goal_option_id(self.goal_id))

    def goal_option(self, goal: Goal) -> Option:
        tasks = self.store.list_tasks(goal_id=goal.id)
        prompt = pretty.goal_entry(goal, tasks, goal.id == self.goal_id, self.unseen.get(goal.id, 0))

        return Option(prompt, id=goal_option_id(goal.id))

    def general_option(self) -> Option:
        prompt = pretty.general_entry(self.goal_id is None, self.unseen.get(None, 0))

        return Option(prompt, id=GENERAL_OPTION)

    def show_goals(self) -> None:
        goal = self.store.get_goal(self.goal_id) if self.goal_id is not None else None
        tasks = self.store.list_tasks(goal_id=goal.id) if goal else []
        key = (goal, tuple(tasks))

        if key == self.details_key:
            return

        self.details_key = key
        self.query_one("#goals", Static).update(goal_details(goal, tasks))


def agent_commands(app: CoopDashboard, agent: Agent) -> Iterable[SystemCommand]:
    yield SystemCommand(
        f"Start {agent.name}",
        f"Open a terminal running {agent.provider or 'its provider'} as {agent.name}",
        lambda name=agent.name: app.start_agent(name, force=True),
    )
    yield SystemCommand(
        f"Remove {agent.name}",
        "Remove the agent from the coop (it can be added again)",
        lambda name=agent.name: app.remove_agent(name),
    )


def latest_goal_id(store: CoopStore) -> Optional[int]:
    goals = store.list_goals() or store.list_goals(include_closed=True)

    return goals[-1].id if goals else None


def goal_option_id(goal_id: Optional[int]) -> str:
    return GENERAL_OPTION if goal_id is None else f"goal-{goal_id}"


def parse_goal_option(option_id: Optional[str]) -> Optional[int]:
    if not option_id or option_id == GENERAL_OPTION:
        return None

    return int(option_id.removeprefix("goal-"))


def goal_details(goal: Optional[Goal], tasks: list[Task]) -> RenderableType:
    if goal is None:
        return Text("Messages that belong to no goal.", style="dim")

    parts = [Text(goal.description, style="dim"), Text()] if goal.description else []

    return Group(*parts, Text("tasks", style="bold"), pretty.task_table(tasks))


def sync_options(listing: OptionList, options: list[Option], fallback: Optional[str] = None) -> None:
    current = [listing.get_option_at_index(index) for index in range(listing.option_count)]

    if [option.id for option in current] == [option.id for option in options]:
        for index, (old, new) in enumerate(zip(current, options)):
            if old.prompt != new.prompt:
                listing.replace_option_prompt_at_index(index, new.prompt)
        return

    highlighted = listing.highlighted_option.id if listing.highlighted_option else fallback
    scroll_y = listing.scroll_y

    listing.set_options(options)
    restore_highlight(listing, highlighted)
    listing.scroll_to(y=scroll_y, animate=False)


def restore_highlight(listing: OptionList, option_id: Optional[str]) -> None:
    ids = [listing.get_option_at_index(index).id for index in range(listing.option_count)]

    if ids:
        listing.highlighted = ids.index(option_id) if option_id in ids else 0


def first_line(text: str) -> str:
    line = text.strip().splitlines()[0] if text.strip() else ""

    return line if len(line) <= 100 else line[:97] + "..."


def parse_composer(text: str) -> tuple[str, str]:
    stripped = text.strip()

    if not stripped.startswith("@"):
        return EVERYONE, stripped

    recipient, _, body = stripped[1:].partition(" ")

    return recipient, body.strip()


def watch(store: CoopStore, backlog: int) -> None:
    CoopDashboard(store, backlog).run()
