import contextlib
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from tkinter import filedialog, ttk
from typing import Any, Callable, Optional

from . import providers, theme
from .errors import CoopError

FIELD_WIDTH = 60
DIALOG_PADDING = 20


@dataclass(frozen=True)
class GoalDraft:
    title: str
    description: str


@dataclass(frozen=True)
class ProjectDraft:
    name: str
    folder: str


@dataclass(frozen=True)
class AgentDraft:
    name: str
    provider: str
    role: str
    workdir: str
    start: bool


class Dialog(tk.Toplevel):
    def __init__(self, parent: tk.Misc, title: str, accept: Callable[[Any], None]):
        super().__init__(parent)
        self.accept = accept

        self.title(title)
        self.transient(parent)
        self.configure(background=theme.current(parent).background)

        self.body = ttk.Frame(self, padding=DIALOG_PADDING)
        self.body.pack(fill="both", expand=True)

        self.bind("<Escape>", lambda event: self.destroy())
        self.bind("<Control-s>", lambda event: self.submit())

    def add_label(self, text: str, first: bool = False) -> None:
        ttk.Label(self.body, text=text, style="Field.TLabel").pack(anchor="w", pady=(0 if first else 12, 4))

    def add_hint(self, text: str = "", above: bool = True) -> ttk.Label:
        hint = ttk.Label(self.body, text=text, style="Hint.TLabel")
        hint.pack(anchor="w", pady=(0, 4) if above else (4, 0))

        return hint

    def add_entry(self, label: str, variable: tk.StringVar, hint: str = "", first: bool = False) -> ttk.Entry:
        self.add_label(label, first)

        if hint:
            self.add_hint(hint)

        entry = ttk.Entry(self.body, textvariable=variable, width=FIELD_WIDTH)
        entry.pack(fill="x")

        return entry

    def add_buttons(self, submit_label: str) -> None:
        self.error = ttk.Label(self.body, style="Error.TLabel", wraplength=420)
        self.error.pack(anchor="w", pady=(10, 0))

        buttons = ttk.Frame(self.body)
        buttons.pack(anchor="e", pady=(12, 0))

        ttk.Button(buttons, text="Cancel", command=self.destroy).pack(side="left", padx=(0, 8))
        ttk.Button(buttons, text=submit_label, command=self.submit, default="active", style="Primary.TButton").pack(side="left")

    def show(self, focus: tk.Widget) -> None:
        self.place_over_parent()
        focus.focus_set()
        self.after_idle(self.grab)

    def place_over_parent(self) -> None:
        self.update_idletasks()

        parent = self.master
        x = parent.winfo_rootx() + max(0, (parent.winfo_width() - self.winfo_reqwidth()) // 2)
        y = parent.winfo_rooty() + max(0, (parent.winfo_height() - self.winfo_reqheight()) // 3)

        self.geometry(f"+{x}+{y}")

    def grab(self) -> None:
        with contextlib.suppress(tk.TclError):
            self.grab_set()

    def submit(self) -> None:
        draft = self.draft()

        if draft is None:
            return

        try:
            self.accept(draft)
        except CoopError as error:
            self.show_error(str(error))
            return

        self.destroy()

    def show_error(self, text: str) -> None:
        self.error.configure(text=text)
        self.bell()

    def draft(self) -> Optional[Any]:
        raise NotImplementedError


class GoalDialog(Dialog):
    def __init__(self, parent: tk.Misc, accept: Callable[[GoalDraft], None]):
        super().__init__(parent, "New goal", accept)
        self.goal_title = tk.StringVar(self)

        title_entry = self.add_entry("Title", self.goal_title, first=True)
        self.description = self.add_description()
        self.add_buttons("Create goal")

        title_entry.bind("<Return>", lambda event: self.description.focus_set())
        self.bind("<Control-Return>", lambda event: self.submit())

        self.show(title_entry)

    def add_description(self) -> tk.Text:
        self.add_label("Description (optional)")
        self.add_hint("Project path, constraints, who does what. Ctrl+Enter creates the goal.")

        options = theme.field_text_options(theme.current(self))
        description = tk.Text(self.body, width=FIELD_WIDTH, height=8, wrap="word", **options)
        description.pack(fill="both", expand=True)

        return description

    def draft(self) -> Optional[GoalDraft]:
        title = self.goal_title.get().strip()

        if not title:
            self.show_error("Give the goal a title.")
            return None

        return GoalDraft(title, self.description.get("1.0", "end").strip())


class AgentDialog(Dialog):
    def __init__(self, parent: tk.Misc, accept: Callable[[AgentDraft], None], taken_names: set[str], default_dir: Path):
        super().__init__(parent, "New agent", accept)
        self.taken_names = taken_names
        self.provider_names = list(providers.PROVIDERS)

        self.role = tk.StringVar(self)
        self.agent_name = tk.StringVar(self)
        self.workdir = tk.StringVar(self, value=str(default_dir))
        self.start = tk.BooleanVar(self, value=True)

        self.provider = self.add_provider_choice()
        role_entry = self.add_entry("Role", self.role, hint="What this agent should focus on")
        self.add_entry("Name", self.agent_name)
        self.name_hint = self.add_hint(above=False)
        self.add_workdir_choice()
        self.add_start_choice()
        self.add_buttons("Create agent")

        self.role.trace_add("write", lambda *args: self.update_suggestion())
        self.provider.bind("<<ComboboxSelected>>", lambda event: self.update_suggestion())
        self.bind("<Return>", lambda event: self.submit())

        self.update_suggestion()
        self.show(role_entry)

    def add_provider_choice(self) -> ttk.Combobox:
        self.add_label("Provider", first=True)

        choice = ttk.Combobox(self.body, values=provider_labels(), state="readonly")
        choice.current(self.provider_names.index(default_provider()))
        choice.pack(fill="x")

        return choice

    def add_workdir_choice(self) -> None:
        self.add_label("Working directory")
        add_folder_choice(self, self.workdir)

    def add_start_choice(self) -> None:
        check = ttk.Checkbutton(self.body, text="Start it now in a new terminal", variable=self.start)
        check.pack(anchor="w", pady=(12, 0))

    def selected_provider(self) -> str:
        return self.provider_names[self.provider.current()]

    def suggestion(self) -> str:
        return providers.suggested_name(self.selected_provider(), self.role.get(), self.taken_names)

    def update_suggestion(self) -> None:
        self.name_hint.configure(text=f"Leave empty to use {self.suggestion()}")

    def draft(self) -> AgentDraft:
        return AgentDraft(
            name=self.agent_name.get().strip() or self.suggestion(),
            provider=self.selected_provider(),
            role=self.role.get().strip(),
            workdir=self.workdir.get().strip(),
            start=self.start.get(),
        )


class ProjectDialog(Dialog):
    def __init__(self, parent: tk.Misc, accept: Callable[[ProjectDraft], None], default_dir: Path):
        super().__init__(parent, "New project", accept)
        self.project_name = tk.StringVar(self)
        self.folder = tk.StringVar(self, value=str(default_dir))

        name_entry = self.add_entry("Name", self.project_name, first=True)
        self.add_label("Folder")
        self.add_hint("Agents of this project start here unless they have their own working directory.")
        add_folder_choice(self, self.folder)
        self.add_hint("The project gets its own team, goals and conversation.", above=False)
        self.add_buttons("Create project")

        self.bind("<Return>", lambda event: self.submit())
        self.show(name_entry)

    def draft(self) -> Optional[ProjectDraft]:
        name = self.project_name.get().strip()

        if not name:
            self.show_error("Give the project a name.")
            return None

        return ProjectDraft(name, self.folder.get().strip())


def add_folder_choice(dialog: Dialog, variable: tk.StringVar) -> None:
    def browse() -> None:
        chosen = filedialog.askdirectory(parent=dialog, initialdir=variable.get(), mustexist=True)

        if chosen:
            variable.set(chosen)

    row = ttk.Frame(dialog.body)
    row.pack(fill="x")

    ttk.Entry(row, textvariable=variable).pack(side="left", fill="x", expand=True)
    ttk.Button(row, text="Browse…", command=browse).pack(side="left", padx=(6, 0))


def provider_labels() -> list[str]:
    installed = {provider.name for provider in providers.installed_providers()}

    return [
        provider.label if provider.name in installed else f"{provider.label} (not installed)"
        for provider in providers.PROVIDERS.values()
    ]


def default_provider() -> str:
    installed = providers.installed_providers()

    return installed[0].name if installed else next(iter(providers.PROVIDERS))
