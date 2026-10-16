from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Checkbox, Input, Label, Select, TextArea

from . import providers

FORM_CSS = """
GoalForm, AgentForm {
    align: center middle;
}

.dialog {
    width: 72;
    max-width: 100%;
    height: auto;
    max-height: 100%;
    border: round $accent;
    border-title-align: left;
    padding: 0 1;
    background: $surface;
}

.dialog Label {
    margin-top: 1;
    color: $text-muted;
}

.dialog TextArea {
    height: 6;
}

.buttons {
    height: auto;
    margin-top: 1;
    align-horizontal: right;
}

.buttons Button {
    margin-left: 1;
}
"""


@dataclass(frozen=True)
class GoalDraft:
    title: str
    description: str


@dataclass(frozen=True)
class AgentDraft:
    name: str
    provider: str
    role: str
    workdir: str
    start: bool


class GoalForm(ModalScreen[Optional[GoalDraft]]):
    DEFAULT_CSS = FORM_CSS
    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("ctrl+s", "submit", "Create", priority=True),
    ]

    def __init__(self, accept: Callable[[GoalDraft], bool]):
        super().__init__()
        self.accept = accept

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog") as dialog:
            dialog.border_title = "New goal"
            yield Label("Title")
            yield Input(placeholder="e.g. Add a grappling hook to the game", id="title")
            yield Label("Description: project path, constraints, who does what (optional)")
            yield TextArea(id="description")

            with Horizontal(classes="buttons"):
                yield Button("Cancel", id="cancel")
                yield Button("Create goal  ^S", variant="primary", id="submit")

    def on_mount(self) -> None:
        self.query_one("#title", Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.query_one("#description", TextArea).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "submit":
            self.action_submit()
        else:
            self.action_cancel()

    def action_submit(self) -> None:
        title = self.query_one("#title", Input).value.strip()

        if not title:
            self.notify("Give the goal a title.", severity="warning")
            self.query_one("#title", Input).focus()
            return

        draft = GoalDraft(title, self.query_one("#description", TextArea).text.strip())

        if self.accept(draft):
            self.dismiss(draft)

    def action_cancel(self) -> None:
        self.dismiss(None)


class AgentForm(ModalScreen[Optional[AgentDraft]]):
    DEFAULT_CSS = FORM_CSS
    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("ctrl+s", "submit", "Create", priority=True),
    ]

    def __init__(self, accept: Callable[[AgentDraft], bool], taken_names: set[str], default_dir: Path):
        super().__init__()
        self.accept = accept
        self.taken_names = taken_names
        self.default_dir = default_dir

    def compose(self) -> ComposeResult:
        installed = [provider.name for provider in providers.installed_providers()]
        options = [
            (provider.label if provider.name in installed else f"{provider.label} (not installed)", provider.name)
            for provider in providers.PROVIDERS.values()
        ]
        default = installed[0] if installed else next(iter(providers.PROVIDERS))

        with Vertical(classes="dialog") as dialog:
            dialog.border_title = "New agent"
            yield Label("Provider")
            yield Select(options, value=default, allow_blank=False, id="provider")
            yield Label("Role: what this agent should focus on")
            yield Input(placeholder="e.g. code reviewer, tests, frontend", id="role")
            yield Label("Name (leave empty to use the suggestion)")
            yield Input(placeholder=self.suggestion(default, ""), id="name")
            yield Label("Working directory")
            yield Input(value=str(self.default_dir), id="workdir")
            yield Checkbox("Start it now in a new terminal", value=True, id="start")

            with Horizontal(classes="buttons"):
                yield Button("Cancel", id="cancel")
                yield Button("Create agent  ^S", variant="primary", id="submit")

    def on_mount(self) -> None:
        self.query_one("#role", Input).focus()

    def suggestion(self, provider: str, role: str) -> str:
        return providers.suggested_name(provider, role, self.taken_names)

    def update_suggestion(self) -> None:
        self.query_one("#name", Input).placeholder = self.suggestion(self.provider(), self.query_one("#role", Input).value)

    def provider(self) -> str:
        return str(self.query_one("#provider", Select).value)

    def on_select_changed(self, event: Select.Changed) -> None:
        self.update_suggestion()

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "role":
            self.update_suggestion()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.action_submit()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "submit":
            self.action_submit()
        else:
            self.action_cancel()

    def action_submit(self) -> None:
        name_input = self.query_one("#name", Input)

        draft = AgentDraft(
            name=name_input.value.strip() or name_input.placeholder,
            provider=self.provider(),
            role=self.query_one("#role", Input).value.strip(),
            workdir=self.query_one("#workdir", Input).value.strip(),
            start=self.query_one("#start", Checkbox).value,
        )

        if self.accept(draft):
            self.dismiss(draft)

    def action_cancel(self) -> None:
        self.dismiss(None)
