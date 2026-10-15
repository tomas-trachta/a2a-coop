import time

from rich.console import Group, RenderableType
from rich.text import Text
from textual import events
from textual.app import App, ComposeResult
from textual.containers import Horizontal, VerticalScroll
from textual.suggester import SuggestFromList
from textual.widgets import Footer, Input, Static

from . import pretty
from .errors import CoopError
from .models import Agent, Message
from .store import EVERYONE, USER, CoopStore

REFRESH_SECONDS = 1.0
SIDEBAR_MIN_TERMINAL_WIDTH = 100

COMPOSER_HINT = "Message everyone, or start with @agent to message one agent  ·  Enter to send"
EMPTY_CONVERSATION_HINT = "Nothing said yet. Type below, or give the agents a goal with `a2a-coop goal add`."

CSS = """
#team {
    height: auto;
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

#sidebar {
    width: 1fr;
    border: round gray;
    border-title-align: left;
    padding: 0 1;
}

.message {
    height: auto;
}

#empty-hint {
    color: gray;
}
"""


class CoopDashboard(App):
    TITLE = "a2a-coop"
    CSS = CSS

    BINDINGS = [
        ("ctrl+q", "quit", "Quit"),
        ("pageup", "scroll_conversation(-1)", "Scroll up"),
        ("pagedown", "scroll_conversation(1)", "Scroll down"),
    ]

    def __init__(self, store: CoopStore, backlog: int):
        super().__init__()
        self.store = store
        self.backlog = backlog
        self.last_message_id = 0
        self.known_agents: tuple[str, ...] = ()

    def compose(self) -> ComposeResult:
        yield Static(id="team")

        with Horizontal(id="main"):
            with VerticalScroll(id="conversation"):
                yield Static(EMPTY_CONVERSATION_HINT, id="empty-hint")

            with VerticalScroll(id="sidebar"):
                yield Static(id="goals")

        yield Input(placeholder=COMPOSER_HINT, id="composer")
        yield Footer()

    def on_mount(self) -> None:
        self.label_panels()
        self.query_one("#conversation", VerticalScroll).anchor()

        self.show_backlog()
        self.refresh_dashboard()
        self.set_interval(REFRESH_SECONDS, self.refresh_dashboard)

        self.query_one("#composer", Input).focus()

    def on_resize(self, event: events.Resize) -> None:
        self.query_one("#sidebar").display = event.size.width >= SIDEBAR_MIN_TERMINAL_WIDTH

    def on_input_submitted(self, event: Input.Submitted) -> None:
        recipient, body = parse_composer(event.value)

        if not body:
            self.notify("Type a message after the @name.", severity="warning")
            return

        if self.send(recipient, body):
            event.input.clear()
            self.refresh_dashboard()

    def action_scroll_conversation(self, direction: int) -> None:
        conversation = self.query_one("#conversation", VerticalScroll)

        if direction < 0:
            conversation.scroll_page_up()
        else:
            conversation.scroll_page_down()

    def send(self, recipient: str, body: str) -> bool:
        try:
            self.store.send_message(USER, recipient, body)
        except CoopError as error:
            self.notify(str(error), severity="error")
            return False

        return True

    def label_panels(self) -> None:
        self.query_one("#team").border_title = "a2a-coop · team"
        self.query_one("#conversation").border_title = "conversation"
        self.query_one("#sidebar").border_title = "goals & tasks"

    def show_backlog(self) -> None:
        recent = self.store.recent_messages(self.backlog) if self.backlog > 0 else []
        self.last_message_id = self.store.latest_message_id()

        self.show_messages(recent)

    def refresh_dashboard(self) -> None:
        self.show_messages(self.store.messages_after(self.last_message_id))
        self.store.take_unread(USER)

        agents = self.store.list_agents()

        self.show_team(agents)
        self.update_suggestions(agents)
        self.show_goals()

    def show_messages(self, messages: list[Message]) -> None:
        if not messages:
            return

        self.remove_empty_hint()
        self.query_one("#conversation").mount_all(Static(pretty.message(item), classes="message") for item in messages)
        self.last_message_id = max(self.last_message_id, messages[-1].id)

    def remove_empty_hint(self) -> None:
        for hint in self.query("#empty-hint"):
            hint.remove()

    def show_team(self, agents: list[Agent]) -> None:
        now = time.time()
        team = self.query_one("#team", Static)

        team.update(team_view(agents, now))
        team.border_subtitle = time.strftime("%H:%M:%S", time.localtime(now))

    def update_suggestions(self, agents: list[Agent]) -> None:
        names = tuple(agent.name for agent in agents)

        if names == self.known_agents:
            return

        self.known_agents = names
        mentions = [f"@{name} " for name in names]
        self.query_one("#composer", Input).suggester = SuggestFromList(mentions, case_sensitive=False)

    def show_goals(self) -> None:
        goals = [(goal, self.store.list_tasks(goal_id=goal.id)) for goal in self.store.list_goals()]
        blocks = [pretty.goal_block(goal, tasks) for goal, tasks in goals]

        self.query_one("#goals", Static).update(Group(*blocks) if blocks else Text("No open goals.", style="dim"))


def team_view(agents: list[Agent], now: float) -> RenderableType:
    if not agents:
        return Text("No agents have joined yet.", style="dim")

    return Group(*(pretty.agent_row(agent, now) for agent in agents))


def parse_composer(text: str) -> tuple[str, str]:
    stripped = text.strip()

    if not stripped.startswith("@"):
        return EVERYONE, stripped

    recipient, _, body = stripped[1:].partition(" ")

    return recipient, body.strip()


def watch(store: CoopStore, backlog: int) -> None:
    CoopDashboard(store, backlog).run()
