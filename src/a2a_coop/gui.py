import contextlib
import signal
import sys
import time
import tkinter as tk
from pathlib import Path
from tkinter import font, messagebox, ttk
from typing import Callable, Optional

from . import events as coop_events
from . import launch, preferences, providers, render, theme
from .dialogs import AgentDialog, AgentDraft, GoalDialog, GoalDraft
from .errors import CoopError
from .models import Agent, Goal, Message, Task
from .store import EVENT, EVERYONE, OFFLINE, QUESTION, USER, CoopStore
from .widgets import (
    Column,
    Row,
    SashPlacer,
    Segment,
    TextPanel,
    add_button,
    append_text,
    button_row,
    card,
    clear_text,
    clip_to_lines,
    color_tags,
    display_lines,
    field_text,
    is_scrolled_to_end,
    recolor_widgets,
    scrolled_text,
    scrolled_tree,
    section_header,
    select_first,
    select_only,
    selected_iid,
    set_enabled,
    surface,
    swatch_image,
    sync_rows,
    wrapping_label,
)

TITLE = "a2a-coop"
SUBTITLE = "Your agents, working together"
REFRESH_MILLISECONDS = 1000
NOTICE_MILLISECONDS = 10000
STARTING_GRACE_SECONDS = 90

DEFAULT_SIZE = (1360, 860)
MINIMUM_SIZE = (1040, 680)
OUTER_PADDING = 16
SIDE_WIDTHS_AT_DEFAULT = (260, 340)
SIDE_WIDTHS_AT_MINIMUM = (232, 280)
GOALS_SHARE = 0.45
QUESTIONS_SHARE_WHILE_WAITING = 0.45
TITLE_LINES = 2
SWATCH_SIZE = 10
SWATCH_GAP = 6
COMPOSER_LINES = (2, 4)

GENERAL_ROW = "general"
PARTICIPANT_TAG = "participant:"
APPEARANCE_LABELS = ("Light", "Dark")
EVERYONE_LABEL = "everyone"
COMPOSER_HINT = "Enter to send  ·  Shift+Enter for a new line"
SHORTCUTS_HINT = "Ctrl+G new goal  ·  Ctrl+N new agent  ·  Ctrl+R answer a question  ·  Esc message box"
EMPTY_CONVERSATION_HINT = "Nothing said about this goal yet."
EMPTY_GENERAL_HINT = "No messages without a goal yet."
NO_GOALS_HINT = "No goals yet. Click New goal… (Ctrl+G) to give the agents one, then start them from the team list."
NO_QUESTIONS_HINT = "No open questions. Agents will ask here when they need you."
NO_AGENTS_HINT = "No agents yet. Add an agent to get started."
NO_AGENT_SELECTED_HINT = "Select an agent to see its role and full status."
GENERAL_DETAILS_HINT = "Select a goal to see its tasks."
NO_TASKS_HINT = "No tasks yet. The agents split the goal into tasks when they start."
NO_TASK_SELECTED_HINT = "Select a task to see its description and result."

GOAL_COLUMNS = (
    Column("goal", "Goal", 150),
    Column("status", "Status", 0, False, shown=False),
    Column("new", "New", 36, False),
)
TEAM_NAME_COLUMN = Column("#0", "Agent", 110)
TEAM_COLUMNS = (Column("agent", "Agent", 0, False, shown=False), Column("presence", "Presence", 88, False))
QUESTION_ASKER_COLUMN = Column("#0", "From", 96, False)
QUESTION_COLUMNS = (Column("asker", "From", 0, False, shown=False), Column("question", "Question", 180))
TASK_COLUMNS = (
    Column("task", "Task", 180),
    Column("state", "State", 0, False, shown=False),
    Column("assignee", "Assignee", 80, False),
)

TASK_STATES = {
    "todo": ("○", "Todo"),
    "in_progress": ("▶", "In progress"),
    "blocked": ("■", "Blocked"),
    "done": ("✓", "Done"),
}

GOAL_ACTIONS = (
    ("Pause", "paused", ("active",)),
    ("Resume", "active", ("paused",)),
    ("Mark done", "done", ("active", "paused")),
    ("Cancel goal…", "cancelled", ("active", "paused")),
)


class IdentityColors:
    def __init__(self, root: tk.Misc, palette: theme.Palette):
        self.root = root
        self.palette = palette
        self.slots: dict[str, int] = {}
        self.swatches: dict[str, tk.PhotoImage] = {}

    def use(self, palette: theme.Palette) -> None:
        self.palette = palette

    def assign(self, names: list[str]) -> None:
        for name in sorted(names):
            self.color(name)

    def color(self, name: str) -> str:
        if name == USER:
            return self.palette.user

        if name == EVERYONE:
            return self.palette.everyone

        if name not in self.slots:
            self.slots[name] = len(self.slots)

        return theme.identity_color(self.palette, self.slots[name])

    def swatch(self, name: str) -> tk.PhotoImage:
        color = self.color(name)

        if color not in self.swatches:
            self.swatches[color] = swatch_image(self.root, color, SWATCH_SIZE, SWATCH_GAP)

        return self.swatches[color]


class CoopDashboard:
    def __init__(self, root: tk.Tk, store: CoopStore, backlog: int, workdir: Optional[Path] = None):
        self.root = root
        self.store = store
        self.backlog = backlog
        self.workdir = workdir or Path.cwd()

        self.last_message_id = 0
        self.agents: list[Agent] = []
        self.question_ids: Optional[tuple[int, ...]] = None
        self.questions: dict[int, Message] = {}
        self.answering: Optional[int] = None
        self.answer_drafts: dict[int, str] = {}
        self.tasks: dict[int, Task] = {}
        self.starting: dict[str, float] = {}
        self.goal_id: Optional[int] = None
        self.unseen: dict[Optional[int], int] = {}
        self.details_key: Optional[tuple] = None
        self.full_title = ""
        self.showing_hint = False
        self.new_below = 0
        self.chosen_tab: Optional[ttk.Frame] = None
        self.jobs: dict[str, str] = {}
        self.preferences_file = preferences.preferences_path(store.path)
        self.appearance = preferences.load_appearance(self.preferences_file)
        self.palette = theme.PALETTES[self.appearance]
        self.colors = IdentityColors(root, self.palette)

        self.build()
        self.bind_keys()
        self.root.bind("<Destroy>", self.forget_jobs, add="+")

        self.colors.assign([agent.name for agent in store.list_agents()])
        self.goal_id = latest_goal_id(store)
        self.load_conversation()
        self.refresh_dashboard()
        self.schedule_refresh()

        self.composer.focus_set()

    def build(self) -> None:
        theme.apply_theme(self.root, self.palette)
        self.configure_window()

        self.show_closed = tk.BooleanVar(self.root, value=False)

        self.build_menu()
        self.build_header()
        self.build_workspace()
        self.build_status_line()

    def configure_window(self) -> None:
        width, height = (theme.scaled(self.root, size) for size in DEFAULT_SIZE)
        min_width, min_height = (theme.scaled(self.root, size) for size in MINIMUM_SIZE)

        self.root.title(TITLE)
        self.root.geometry(f"{width}x{height}")
        self.root.minsize(min_width, min_height)

        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(1, weight=1)

    def build_menu(self) -> None:
        menu = tk.Menu(self.root, tearoff=False)
        coop = tk.Menu(menu, tearoff=False)

        coop.add_command(label="New goal…", accelerator="Ctrl+G", command=self.new_goal)
        coop.add_command(label="New agent…", accelerator="Ctrl+N", command=self.new_agent)
        coop.add_separator()
        coop.add_command(label="Quit", accelerator="Ctrl+Q", command=self.root.quit)

        menu.add_cascade(label="Coop", menu=coop)
        self.root.configure(menu=menu)

    def build_header(self) -> None:
        padding = theme.scaled(self.root, OUTER_PADDING)
        header = ttk.Frame(self.root, padding=(padding, padding - 4, padding, 12))
        header.grid(row=0, column=0, sticky="ew")

        ttk.Label(header, text=TITLE, style="Title.TLabel").pack(side="left")
        ttk.Label(header, text=SUBTITLE, style="Subtitle.TLabel").pack(side="left", anchor="s", padx=(12, 0), pady=(0, 4))

        add_button(header, "New agent…", self.new_agent, side="right")
        add_button(header, "New goal…", self.new_goal, primary=True, side="right", padx=(0, 8))
        self.build_appearance_choice(header)

    def build_appearance_choice(self, parent: tk.Misc) -> None:
        self.appearance_choice = ttk.Combobox(parent, values=APPEARANCE_LABELS, state="readonly", width=6)
        self.appearance_choice.set(appearance_label(self.appearance))
        self.appearance_choice.pack(side="right", padx=(0, 20))
        self.appearance_choice.bind("<<ComboboxSelected>>", lambda event: self.appearance_selected())

        ttk.Label(parent, text="Appearance", style="Subtitle.TLabel").pack(side="right", padx=(0, 6))

    def build_status_line(self) -> None:
        padding = theme.scaled(self.root, OUTER_PADDING)

        self.notice = ttk.Label(self.root, text=SHORTCUTS_HINT, style="Status.TLabel", anchor="w", padding=(padding, 6, padding, 8))
        self.notice.grid(row=2, column=0, sticky="ew")

    def build_workspace(self) -> None:
        self.workspace = ttk.PanedWindow(self.root, orient="horizontal")
        self.workspace.grid(row=1, column=0, sticky="nsew", padx=theme.scaled(self.root, OUTER_PADDING))

        self.workspace.add(self.build_left_column(self.workspace), weight=0)
        self.workspace.add(self.build_conversation(self.workspace), weight=1)
        self.workspace.add(self.build_right_column(self.workspace), weight=0)

        self.column_placer = SashPlacer(self.workspace, self.column_sashes)

    def build_left_column(self, parent: tk.Misc) -> ttk.PanedWindow:
        column = ttk.PanedWindow(parent, orient="vertical")

        column.add(self.build_goals(column), weight=1)
        column.add(self.build_team(column), weight=1)

        self.left_placer = SashPlacer(column, lambda height: (round(height * GOALS_SHARE),))

        return column

    def build_right_column(self, parent: tk.Misc) -> ttk.PanedWindow:
        column = ttk.PanedWindow(parent, orient="vertical")

        column.add(self.build_questions(column), weight=0)
        column.add(self.build_goal_details(column), weight=1)

        self.right_placer = SashPlacer(column, self.question_sashes)

        return column

    def column_sashes(self, width: int) -> tuple[int, int]:
        narrowest, widest = (theme.scaled(self.root, size[0] - 2 * OUTER_PADDING) for size in (MINIMUM_SIZE, DEFAULT_SIZE))
        left, right = (theme.scaled(self.root, side) for side in side_widths(width, narrowest, widest))

        return left, width - right - theme.scaled(self.root, theme.PANE_GAP)

    def question_sashes(self, height: int) -> tuple[int]:
        if self.questions:
            return (round(height * QUESTIONS_SHARE_WHILE_WAITING),)

        return (min(self.questions_card.winfo_reqheight(), height // 2),)

    def build_goals(self, parent: tk.Misc) -> ttk.Frame:
        frame = card(parent)
        header, _ = section_header(frame, "Goals")

        show_closed = ttk.Checkbutton(header, text="Show closed", variable=self.show_closed, command=self.refresh_dashboard)
        show_closed.configure(style="Card.TCheckbutton")
        show_closed.pack(side="right")

        self.goal_list = scrolled_tree(frame, GOAL_COLUMNS, height=6)
        color_tags(self.goal_list, goal_status_colors(self.palette))
        self.goal_list.bind("<<TreeviewSelect>>", lambda event: self.goal_selected())

        return frame

    def build_team(self, parent: tk.Misc) -> ttk.Frame:
        frame = card(parent)
        header, _ = section_header(frame, "Team")

        self.team_count = ttk.Label(header, style="Muted.Card.TLabel")
        self.team_count.pack(side="right")

        buttons = button_row(frame, side="bottom")
        self.start_button = add_button(buttons, "Start", self.start_selected_agent)
        add_button(buttons, "Add…", self.new_agent)
        self.remove_button = add_button(buttons, "Remove…", self.remove_selected_agent)

        self.team = scrolled_tree(frame, TEAM_COLUMNS, height=4, tree_column=TEAM_NAME_COLUMN)
        self.team.master.pack_configure(fill="x", expand=False)
        color_tags(self.team, presence_colors(self.palette))

        self.agent_details = TextPanel(frame, height=4)
        self.agent_details.frame.pack(side="top", fill="both", expand=True, pady=(10, 0))
        configure_detail_tags(self.agent_details.text, self.palette)

        self.team.bind("<<TreeviewSelect>>", lambda event: self.show_selected_agent())
        self.team.bind("<Double-1>", lambda event: self.start_selected_agent())
        self.team.bind("<Return>", lambda event: self.start_selected_agent())

        return frame

    def build_conversation(self, parent: tk.Misc) -> ttk.Frame:
        frame = card(parent)

        self.build_conversation_header(frame)
        self.build_composer(frame)
        ttk.Separator(frame).pack(side="bottom", fill="x", pady=(12, 0))
        self.build_chat(frame)

        return frame

    def build_conversation_header(self, parent: tk.Misc) -> None:
        header = surface(parent)
        header.pack(side="top", fill="x", pady=(0, 10))

        self.conversation_title = ttk.Label(header, style="GoalTitle.Card.TLabel", justify="left", anchor="w")
        self.conversation_title.pack(side="top", fill="x")
        self.conversation_title.bind("<Configure>", lambda event: self.fit_conversation_title())

        self.conversation_summary = ttk.Label(header, style="Muted.Card.TLabel")
        self.conversation_summary.pack(side="top", fill="x", pady=(2, 0))

        ttk.Separator(parent).pack(side="top", fill="x")

    def build_chat(self, parent: tk.Misc) -> None:
        frame, self.conversation = scrolled_text(parent, height=10, on_scroll=self.chat_scrolled)
        frame.pack(side="top", fill="both", expand=True, pady=(4, 0))

        self.conversation.configure(padx=4, pady=4, spacing2=3)
        configure_conversation_tags(self.conversation, self.palette)

        self.jump_button = ttk.Button(frame, style="Jump.Primary.TButton", command=self.jump_to_latest)

    def build_composer(self, parent: tk.Misc) -> None:
        composer = surface(parent)
        composer.pack(side="bottom", fill="x", pady=(10, 0))

        heading = surface(composer)
        heading.pack(side="top", fill="x")

        self.composer_scope = ttk.Label(heading, style="Field.Card.TLabel")
        self.composer_scope.pack(side="left")
        ttk.Label(heading, text=COMPOSER_HINT, style="Muted.Card.TLabel").pack(side="right")

        self.build_composer_input(composer)
        self.build_composer_actions(composer)

    def build_composer_input(self, parent: tk.Misc) -> None:
        frame, self.composer = field_text(parent, height=COMPOSER_LINES[0])
        frame.pack(side="top", fill="x", pady=(6, 0))

        for key in ("<Return>", "<KP_Enter>"):
            self.composer.bind(key, lambda event: self.send_message() or "break")

        self.composer.bind("<Shift-Return>", lambda event: self.insert_new_line())
        self.composer.bind("<<Modified>>", lambda event: self.composer_changed())
        self.composer.bind("<Configure>", lambda event: self.fit_composer())
        self.composer.bind("<Tab>", lambda event: focus_next(event.widget))
        self.composer.bind("<Shift-Tab>", lambda event: focus_previous(event.widget))

    def build_composer_actions(self, parent: tk.Misc) -> None:
        row = button_row(parent, pady=(8, 0))
        ttk.Label(row, text="To", style="Muted.Card.TLabel").pack(side="left", padx=(0, 6))

        self.recipient = ttk.Combobox(row, values=[EVERYONE_LABEL], state="readonly", width=16)
        self.recipient.set(EVERYONE_LABEL)
        self.recipient.pack(side="left")

        add_button(row, "Send", self.send_message, primary=True, side="right", padx=0)

    def build_questions(self, parent: tk.Misc) -> ttk.Frame:
        self.questions_card = card(parent)
        _, self.questions_heading = section_header(self.questions_card, "Questions for you")

        self.build_answer_area(self.questions_card)

        self.question_hint = wrapping_label(self.questions_card)
        self.question_hint.configure(text=NO_QUESTIONS_HINT)

        self.question_area = surface(self.questions_card)
        self.question_list = scrolled_tree(self.question_area, QUESTION_COLUMNS, height=2, tree_column=QUESTION_ASKER_COLUMN)
        self.question_list.master.pack_configure(fill="x", expand=False)
        self.question_list.bind("<<TreeviewSelect>>", lambda event: self.show_selected_question())

        self.question_text = TextPanel(self.question_area, height=5)
        self.question_text.frame.pack(side="top", fill="both", expand=True, pady=(10, 0))
        configure_detail_tags(self.question_text.text, self.palette)

        return self.questions_card

    def build_answer_area(self, parent: tk.Misc) -> None:
        area = surface(parent)
        area.pack(side="bottom", fill="x", pady=(10, 0))

        row = button_row(area, pady=(0, 6))
        ttk.Label(row, text="Your answer", style="Field.Card.TLabel").pack(side="left", anchor="s")

        self.question_buttons = (
            add_button(row, "Answer", self.answer, primary=True, side="right"),
            add_button(row, "Dismiss", self.dismiss_question, side="right", padx=(0, 6)),
        )

        self.answer_box = ttk.Entry(area)
        self.answer_box.pack(side="top", fill="x")
        self.answer_box.bind("<Return>", lambda event: self.answer())

    def build_goal_details(self, parent: tk.Misc) -> ttk.Frame:
        frame = card(parent)
        section_header(frame, "Goal details")

        self.build_goal_actions(frame)

        self.inspector = ttk.Notebook(frame)
        self.inspector.pack(side="top", fill="both", expand=True)

        self.overview_tab = self.build_overview_tab(self.inspector)
        self.tasks_tab = self.build_tasks_tab(self.inspector)
        self.inspector.add(self.overview_tab, text="Overview")
        self.inspector.add(self.tasks_tab, text="Tasks")

        for sequence in ("<ButtonRelease-1>", "<KeyRelease-Left>", "<KeyRelease-Right>"):
            self.inspector.bind(sequence, lambda event: self.remember_tab(), add="+")

        return frame

    def build_overview_tab(self, notebook: ttk.Notebook) -> ttk.Frame:
        tab = ttk.Frame(notebook, style="Surface.TFrame", padding=10)

        self.overview_progress = ttk.Label(tab, style="Field.Card.TLabel")
        self.overview_progress.pack(side="top", fill="x", pady=(0, 6))

        self.goal_details = TextPanel(tab, height=3)
        self.goal_details.frame.pack(side="top", fill="both", expand=True)
        configure_detail_tags(self.goal_details.text, self.palette)

        return tab

    def build_tasks_tab(self, notebook: ttk.Notebook) -> ttk.Frame:
        tab = ttk.Frame(notebook, style="Surface.TFrame", padding=10)

        self.task_summary = ttk.Label(tab, style="Field.Card.TLabel")
        self.task_summary.pack(side="top", fill="x", pady=(0, 6))

        split = ttk.PanedWindow(tab, orient="vertical")
        split.pack(side="top", fill="both", expand=True)

        tasks = surface(split)
        self.task_list = scrolled_tree(tasks, TASK_COLUMNS, height=3, headings=True)
        self.task_list.tag_configure("done", foreground=self.palette.secondary)
        self.task_list.bind("<<TreeviewSelect>>", lambda event: self.show_selected_task())

        self.task_details = TextPanel(split, height=3)
        configure_detail_tags(self.task_details.text, self.palette)

        split.add(tasks, weight=1)
        split.add(self.task_details.frame, weight=1)

        return tab

    def build_goal_actions(self, parent: tk.Misc) -> None:
        actions = button_row(parent, side="bottom", pady=(12, 0))

        self.goal_buttons = {
            status: add_button(actions, label, lambda status=status: self.goal_action(status))
            for label, status, allowed in GOAL_ACTIONS
        }
        self.goal_buttons["cancelled"].pack_configure(side="right", padx=0)

    def bind_keys(self) -> None:
        bind_shortcut(self.root, "g", self.new_goal)
        bind_shortcut(self.root, "n", self.new_agent)
        bind_shortcut(self.root, "r", self.focus_answer)
        bind_shortcut(self.root, "q", self.root.quit)

        self.root.bind("<Escape>", lambda event: self.composer.focus_set())

    def later(self, name: str, milliseconds: Optional[int], action: Callable[[], object]) -> None:
        self.cancel_job(name)

        def run() -> None:
            self.jobs.pop(name, None)
            action()

        self.jobs[name] = self.root.after_idle(run) if milliseconds is None else self.root.after(milliseconds, run)

    def cancel_job(self, name: str) -> None:
        job = self.jobs.pop(name, None)

        if job is not None:
            self.root.after_cancel(job)

    def forget_jobs(self, event: tk.Event) -> None:
        if event.widget is not self.root:
            return

        for name in list(self.jobs):
            self.cancel_job(name)

    def schedule_refresh(self) -> None:
        self.later("refresh", REFRESH_MILLISECONDS, self.refresh_periodically)

    def refresh_periodically(self) -> None:
        try:
            self.refresh_dashboard()
        finally:
            self.schedule_refresh()

    def refresh_dashboard(self) -> None:
        self.forget_removed_goal()
        self.receive(self.store.messages_after(self.last_message_id))
        self.store.take_unread(USER)

        self.agents = self.store.list_agents()

        self.show_team()
        self.show_recipients()
        self.show_questions(self.store.open_questions())
        self.show_goal_list()
        self.show_goal_details()

    def forget_removed_goal(self) -> None:
        if self.goal_id is not None and self.current_goal() is None:
            self.goal_id = None
            self.load_conversation()

    def current_goal(self) -> Optional[Goal]:
        if self.goal_id is None:
            return None

        try:
            return self.store.get_goal(self.goal_id)
        except CoopError:
            return None

    def load_conversation(self) -> None:
        clear_text(self.conversation)
        self.showing_hint = False
        self.set_new_below(0)

        self.last_message_id = self.store.latest_message_id()
        recent = self.store.goal_messages(self.goal_id, self.backlog) if self.backlog > 0 else []

        if recent:
            self.show_messages(recent)
        else:
            self.show_hint(self.empty_hint())

    def empty_hint(self) -> str:
        if self.goal_id is not None:
            return EMPTY_CONVERSATION_HINT

        if not self.store.list_goals(include_closed=True):
            return NO_GOALS_HINT

        return EMPTY_GENERAL_HINT

    def show_hint(self, hint: str) -> None:
        append_text(self.conversation, hint, ("hint",))
        self.showing_hint = True

    def show_conversation_header(self, goal: Optional[Goal], tasks: list[Task]) -> None:
        self.full_title = conversation_title(goal)

        self.fit_conversation_title()
        self.conversation_summary.configure(text=conversation_summary(goal, tasks))
        self.composer_scope.configure(text=composer_scope(goal))

    def fit_conversation_title(self) -> None:
        width = self.conversation_title.winfo_width()
        clipped = clip_to_lines(self.full_title, theme.GOAL_TITLE_FONT, width, TITLE_LINES)

        self.conversation_title.configure(text=clipped, wraplength=max(width, 200))

    def receive(self, messages: list[Message]) -> None:
        if not messages:
            return

        self.last_message_id = max(self.last_message_id, messages[-1].id)
        current = [message for message in messages if message.goal_id == self.goal_id]

        if not self.show_messages(current):
            self.set_new_below(self.new_below + len(current))

        self.count_unseen(messages)

    def count_unseen(self, messages: list[Message]) -> None:
        for message in messages:
            if message.goal_id != self.goal_id and message.sender != USER:
                self.unseen[message.goal_id] = self.unseen.get(message.goal_id, 0) + 1

    def show_messages(self, messages: list[Message]) -> bool:
        if not messages:
            return True

        following = self.showing_hint or is_scrolled_to_end(self.conversation)

        if self.showing_hint:
            clear_text(self.conversation)
            self.showing_hint = False

        for message in messages:
            append_message(self.conversation, message, self.participant_tag)

        if following:
            self.conversation.yview_moveto(1.0)

        return following

    def chat_scrolled(self, first: float, last: float) -> None:
        if last >= 0.999 and self.new_below:
            self.set_new_below(0)

    def set_new_below(self, count: int) -> None:
        self.new_below = count

        if count:
            self.jump_button.configure(text=new_messages_label(count))
            self.jump_button.place(relx=0.5, rely=1.0, anchor="s", y=-10)
            self.jump_button.lift()
            return

        if self.root.focus_get() is self.jump_button:
            self.composer.focus_set()

        self.jump_button.place_forget()

    def jump_to_latest(self) -> None:
        self.conversation.yview_moveto(1.0)
        self.set_new_below(0)

    def show_team(self) -> None:
        now = time.time()

        self.forget_started_agents(now)
        sync_rows(self.team, [self.agent_row(agent, now) for agent in self.agents])
        select_first(self.team)

        self.team_count.configure(text=str(len(self.agents)) if self.agents else "")
        self.show_selected_agent()

    def agent_row(self, agent: Agent, now: float) -> Row:
        starting = agent.name in self.starting
        presence = "starting…" if starting else render.presence(agent, now)

        tags = (presence_tag(agent, now, starting),)

        return Row(agent.name, (agent.name, presence), tags, agent.name, self.colors.swatch(agent.name))

    def question_row(self, question: Message) -> Row:
        values = (question.sender, first_line(question.body))

        return Row(str(question.id), values, (), question.sender, self.colors.swatch(question.sender))

    def identity_tag(self, text: tk.Text, name: str) -> str:
        tag = f"{PARTICIPANT_TAG}{name}"
        text.tag_configure(tag, foreground=self.colors.color(name), font=theme.BOLD_FONT)

        return tag

    def participant_tag(self, name: str) -> str:
        return self.identity_tag(self.conversation, name)

    def forget_started_agents(self, now: float) -> None:
        for agent in self.agents:
            started = self.starting.get(agent.name)

            if started is None:
                continue

            joined = agent.activity != OFFLINE and agent.last_seen >= started
            if joined or now - started > STARTING_GRACE_SECONDS:
                del self.starting[agent.name]

    def show_selected_agent(self) -> None:
        name = selected_iid(self.team)
        agent = next((agent for agent in self.agents if agent.name == name), None)

        name_tag = self.identity_tag(self.agent_details.text, agent.name) if agent else ""

        self.agent_details.show(agent_details(agent, bool(self.agents), name_tag))

        for button in (self.start_button, self.remove_button):
            set_enabled(button, agent is not None)

    def show_recipients(self) -> None:
        choices = [EVERYONE_LABEL, *(agent.name for agent in self.agents)]

        if list(self.recipient.cget("values")) == choices:
            return

        self.recipient.configure(values=choices)

        if self.recipient.get() not in choices:
            self.recipient.set(EVERYONE_LABEL)

    def show_questions(self, questions: list[Message]) -> None:
        ids = tuple(question.id for question in questions)

        if ids == self.question_ids:
            return

        self.announce_new_questions(questions)
        was_waiting = bool(self.questions)

        self.question_ids = ids
        self.questions = {question.id: question for question in questions}

        sync_rows(self.question_list, [self.question_row(question) for question in questions])
        select_first(self.question_list)

        self.mark_waiting(len(questions))
        self.show_question_area(was_waiting)
        self.show_selected_question()
        self.forget_stale_drafts()

    def announce_new_questions(self, questions: list[Message]) -> None:
        if self.question_ids is None:
            return

        for question in questions:
            if question.id not in self.question_ids:
                self.root.bell()
                self.notify(f"{question.sender} asks you: {first_line(question.body)}")

    def mark_waiting(self, count: int) -> None:
        if count:
            self.questions_heading.configure(text=f"Questions for you ({count})", style="Waiting.Heading.Card.TLabel")
            self.root.title(f"{TITLE} · {count} question{'s' if count > 1 else ''} waiting")
            return

        self.questions_heading.configure(text="Questions for you", style="Heading.Card.TLabel")
        self.root.title(TITLE)

    def show_question_area(self, was_waiting: bool) -> None:
        waiting = bool(self.questions)

        if waiting:
            self.question_hint.pack_forget()
            self.question_area.pack(side="top", fill="both", expand=True)
        else:
            self.question_area.pack_forget()
            self.question_hint.pack(side="top", fill="x")

        if waiting != was_waiting:
            self.later("questions-sash", None, self.right_placer.reset)

    def selected_question(self) -> Optional[int]:
        iid = selected_iid(self.question_list)

        return int(iid) if iid is not None else None

    def show_selected_question(self) -> None:
        question = self.questions.get(self.selected_question())

        set_enabled(self.answer_box, True)
        self.switch_answer_draft(question.id if question else None)
        asker_tag = self.identity_tag(self.question_text.text, question.sender) if question else ""

        self.question_text.show(question_details(question, asker_tag))

        for widget in (self.answer_box, *self.question_buttons):
            set_enabled(widget, question is not None)

    def switch_answer_draft(self, target: Optional[int]) -> None:
        if target == self.answering:
            return

        draft = self.answer_box.get()

        if self.answering is not None and draft.strip():
            self.answer_drafts[self.answering] = draft

        self.answering = target
        self.answer_box.delete(0, "end")
        self.answer_box.insert(0, self.answer_drafts.pop(target, "") if target is not None else "")

    def forget_stale_drafts(self) -> None:
        self.answer_drafts = {target: draft for target, draft in self.answer_drafts.items() if target in self.questions}

    def show_goal_list(self) -> None:
        goals = [goal for goal in self.store.list_goals(include_closed=True) if self.is_listed(goal)]
        rows = [*(self.goal_row(goal) for goal in reversed(goals)), self.general_row()]

        sync_rows(self.goal_list, rows)
        select_only(self.goal_list, goal_row_id(self.goal_id))

    def is_listed(self, goal: Goal) -> bool:
        return self.show_closed.get() or goal.status in ("active", "paused") or goal.id == self.goal_id

    def goal_row(self, goal: Goal) -> Row:
        values = (goal_label(goal), status_word(goal.status), unseen_badge(self.unseen.get(goal.id, 0)))

        return Row(goal_row_id(goal.id), values, (goal.status,))

    def general_row(self) -> Row:
        return Row(GENERAL_ROW, ("General", "", unseen_badge(self.unseen.get(None, 0))), ("general",))

    def show_goal_details(self) -> None:
        goal = self.current_goal()
        tasks = self.store.list_tasks(goal_id=goal.id) if goal else []
        key = (goal, tuple(tasks))

        if key == self.details_key:
            return

        self.details_key = key
        self.tasks = {task.id: task for task in tasks}

        self.show_conversation_header(goal, tasks)
        self.goal_details.show(goal_details(goal))
        self.overview_progress.configure(text=task_progress(tasks) if goal else "")
        self.task_summary.configure(text=task_progress(tasks))
        sync_rows(self.task_list, [task_row(task) for task in tasks])
        self.show_selected_task()
        self.show_inspector_tab(goal, tasks)
        self.update_goal_buttons(goal)

    def show_inspector_tab(self, goal: Optional[Goal], tasks: list[Task]) -> None:
        self.inspector.tab(self.tasks_tab, text=tasks_tab_label(tasks), state="normal" if goal else "disabled")

        if goal is None:
            self.inspector.select(self.overview_tab)
            return

        if self.chosen_tab is None:
            self.chosen_tab = self.tasks_tab if tasks else self.overview_tab

        self.inspector.select(self.chosen_tab)

    def remember_tab(self) -> None:
        if self.goal_id is not None:
            self.chosen_tab = self.inspector.nametowidget(self.inspector.select())

    def show_selected_task(self) -> None:
        iid = selected_iid(self.task_list)
        task = self.tasks.get(int(iid)) if iid is not None else None

        self.task_details.show(task_details(task, bool(self.tasks)))

    def update_goal_buttons(self, goal: Optional[Goal]) -> None:
        for label, status, allowed in GOAL_ACTIONS:
            set_enabled(self.goal_buttons[status], goal is not None and goal.status in allowed)

        self.show_pause_or_resume(goal is not None and goal.status == "paused")

    def show_pause_or_resume(self, paused: bool) -> None:
        shown, hidden = ("active", "paused") if paused else ("paused", "active")

        self.goal_buttons[hidden].pack_forget()
        self.goal_buttons[shown].pack(side="left", padx=(0, 6), before=self.goal_buttons["done"])

    def goal_selected(self) -> None:
        iid = selected_iid(self.goal_list)

        if iid is None:
            return

        goal_id = parse_goal_row(iid)

        if goal_id != self.goal_id:
            self.open_goal(goal_id)

    def open_goal(self, goal_id: Optional[int]) -> None:
        self.goal_id = goal_id
        self.unseen.pop(goal_id, None)

        self.load_conversation()
        self.refresh_dashboard()

    def send_message(self) -> None:
        body = self.composer.get("1.0", "end-1c").strip()
        recipient = recipient_name(self.recipient.get())

        if not body:
            return

        if self.attempt(lambda: self.store.send_message(USER, recipient, body, goal_id=self.goal_id)):
            self.clear_composer()
            self.refresh_dashboard()

    def clear_composer(self) -> None:
        self.composer.delete("1.0", "end")
        self.composer.edit_reset()
        self.fit_composer()

    def insert_new_line(self) -> str:
        replace_selection(self.composer, "\n")
        self.composer.see("insert")

        return "break"

    def composer_changed(self) -> None:
        self.composer.edit_modified(False)
        self.fit_composer()

    def fit_composer(self) -> None:
        fewest, most = COMPOSER_LINES
        lines = min(max(display_lines(self.composer), fewest), most)

        if int(self.composer.cget("height")) != lines:
            self.composer.configure(height=lines)

    def answer(self) -> None:
        target = self.selected_question()
        text = self.answer_box.get().strip()

        if target is None or not text:
            return

        if self.attempt(lambda: self.store.answer_question(target, text)):
            self.answer_box.delete(0, "end")
            self.answer_drafts.pop(target, None)
            self.refresh_dashboard()

    def dismiss_question(self) -> None:
        target = self.selected_question()

        if target is not None and self.attempt(lambda: self.store.dismiss_question(target)):
            self.refresh_dashboard()

    def focus_answer(self) -> None:
        if not self.questions:
            self.notify("No questions are waiting for you.")
            return

        self.answer_box.focus_set()

    def new_goal(self) -> GoalDialog:
        return GoalDialog(self.root, self.create_goal)

    def new_agent(self) -> AgentDialog:
        taken = {agent.name for agent in self.agents}

        return AgentDialog(self.root, self.create_agent, taken, self.workdir)

    def create_goal(self, draft: GoalDraft) -> None:
        goal = self.store.create_goal(draft.title, draft.description)
        self.store.announce(USER, coop_events.goal_created(goal), goal.id)

        self.open_goal(goal.id)

    def create_agent(self, draft: AgentDraft) -> None:
        workdir = providers.normalize_workdir(draft.workdir)
        self.store.define_agent(draft.name, draft.provider, draft.role, workdir)

        self.notify(f"Added agent {draft.name}.")
        self.refresh_dashboard()
        select_only(self.team, draft.name)

        if draft.start:
            self.start_agent(draft.name)

    def goal_action(self, status: str) -> None:
        if status == "cancelled":
            self.cancel_goal()
            return

        self.set_goal_status(status)

    def cancel_goal(self) -> None:
        goal = self.current_goal()

        if goal is not None and self.confirm(cancel_question(goal)):
            self.set_goal_status("cancelled")

    def set_goal_status(self, status: str) -> None:
        def change() -> None:
            goal = self.store.set_goal_status(self.goal_id, status)
            self.store.announce(USER, coop_events.goal_status_changed(goal), goal.id)

        if self.goal_id is not None and self.attempt(change):
            self.refresh_dashboard()

    def selected_agent(self) -> Optional[str]:
        name = selected_iid(self.team)

        if name is None:
            self.notify("Select an agent in the team list first.")

        return name

    def start_selected_agent(self) -> None:
        name = self.selected_agent()

        if name is not None:
            self.start_agent(name)

    def start_agent(self, name: str) -> None:
        if self.is_running(name) and not self.confirm(f"{name} is already running. Start another copy?"):
            return

        self.attempt(lambda: self.launch_agent(name))

    def is_running(self, name: str) -> bool:
        now = time.time()

        return any(agent.name == name and render.is_online(agent, now) for agent in self.agents)

    def launch_agent(self, name: str) -> None:
        where = launch.start_in_window(self.store.path, self.store.get_agent(name), self.workdir)

        self.starting[name] = time.time()
        self.notify(f"Starting {name} in {where}.")
        self.refresh_dashboard()

    def remove_selected_agent(self) -> None:
        name = self.selected_agent()

        if name is None or not self.confirm(f"Remove {name} from the coop? It can be added again later."):
            return

        if self.attempt(lambda: self.store.remove_agent(name)):
            self.notify(f"Removed {name}.")
            self.refresh_dashboard()

    def confirm(self, question: str) -> bool:
        return messagebox.askyesno(TITLE, question, parent=self.root)

    def attempt(self, action: Callable[[], object]) -> bool:
        try:
            action()
        except CoopError as error:
            self.notify(str(error), error=True)
            return False

        return True

    def notify(self, text: str, error: bool = False) -> None:
        self.notice.configure(text=text, style="Error.Status.TLabel" if error else "Status.TLabel")

        if error:
            self.root.bell()

        self.later("notice", NOTICE_MILLISECONDS, self.clear_notice)

    def appearance_selected(self) -> None:
        self.choose_appearance(self.appearance_choice.get().lower())

    def choose_appearance(self, appearance: str) -> None:
        if appearance == self.appearance:
            return

        self.use_appearance(appearance)
        self.remember_appearance(appearance)

    def use_appearance(self, appearance: str) -> None:
        self.appearance = appearance
        self.palette = theme.PALETTES[appearance]
        self.appearance_choice.set(appearance_label(appearance))

        theme.apply_theme(self.root, self.palette)
        recolor_widgets(self.root, self.palette)
        self.colors.use(self.palette)
        self.recolor_tags()
        self.recolor_identity_rows()

    def remember_appearance(self, appearance: str) -> None:
        try:
            preferences.save_appearance(self.preferences_file, appearance)
        except OSError:
            self.notify(f"Using {appearance} mode for this session; could not save appearance.", error=True)

    def detail_texts(self) -> list[tk.Text]:
        return [panel.text for panel in (self.agent_details, self.question_text, self.goal_details, self.task_details)]

    def recolor_tags(self) -> None:
        configure_conversation_tags(self.conversation, self.palette)

        for detail in self.detail_texts():
            configure_detail_tags(detail, self.palette)

        for widget in (self.conversation, *self.detail_texts()):
            self.recolor_identity_tags(widget)

        color_tags(self.team, presence_colors(self.palette))
        color_tags(self.goal_list, goal_status_colors(self.palette))
        self.task_list.tag_configure("done", foreground=self.palette.secondary)

    def recolor_identity_tags(self, text: tk.Text) -> None:
        for tag in text.tag_names():
            if tag.startswith(PARTICIPANT_TAG):
                self.identity_tag(text, tag.removeprefix(PARTICIPANT_TAG))

    def recolor_identity_rows(self) -> None:
        self.show_team()
        sync_rows(self.question_list, [self.question_row(question) for question in self.questions.values()])

    def clear_notice(self) -> None:
        self.notice.configure(text=SHORTCUTS_HINT, style="Status.TLabel")


def side_widths(width: int, narrowest: int, widest: int) -> tuple[int, int]:
    progress = min(max((width - narrowest) / max(widest - narrowest, 1), 0.0), 1.0)

    return tuple(
        round(at_minimum + (at_default - at_minimum) * progress)
        for at_minimum, at_default in zip(SIDE_WIDTHS_AT_MINIMUM, SIDE_WIDTHS_AT_DEFAULT)
    )


def presence_colors(palette: theme.Palette) -> dict[str, str]:
    return {
        "listening": palette.success,
        "busy": palette.warning,
        "stale": palette.error,
        "offline": palette.secondary,
    }


def goal_status_colors(palette: theme.Palette) -> dict[str, str]:
    return {
        "paused": palette.warning,
        "done": palette.secondary,
        "cancelled": palette.secondary,
        "general": palette.secondary,
    }


def appearance_label(appearance: str) -> str:
    return appearance.capitalize()


def configure_conversation_tags(text: tk.Text, palette: theme.Palette) -> None:
    text.tag_configure("hint", foreground=palette.secondary)
    text.tag_configure("muted", foreground=palette.secondary)
    text.tag_configure("entry", spacing1=12)
    text.tag_configure("event", foreground=palette.secondary, lmargin2=event_indent())
    text.tag_configure("event-more", lmargin1=event_indent())
    text.tag_configure("body", lmargin1=12, lmargin2=12, spacing1=4)
    text.tag_configure("question", background=palette.question_background, lmargin1=12, lmargin2=12, rmargin=4)
    text.tag_configure("question-mark", foreground=palette.warning, font=theme.BOLD_FONT)


def configure_detail_tags(text: tk.Text, palette: theme.Palette) -> None:
    text.tag_configure("strong", font=theme.BOLD_FONT)
    text.tag_configure("muted", foreground=palette.secondary)
    text.tag_configure("paragraph", spacing1=8)


def event_indent() -> int:
    return font.nametofont(theme.TEXT_FONT).measure(f"{render.clock(0)}  •  ")


def replace_selection(text: tk.Text, content: str) -> None:
    if text.tag_ranges("sel") and text.compare("sel.first", "<=", "insert") and text.compare("sel.last", ">=", "insert"):
        text.delete("sel.first", "sel.last")

    text.insert("insert", content)


def focus_next(widget: tk.Misc) -> str:
    widget.tk_focusNext().focus_set()

    return "break"


def focus_previous(widget: tk.Misc) -> str:
    widget.tk_focusPrev().focus_set()

    return "break"


def bind_shortcut(root: tk.Tk, key: str, action: Callable[[], object]) -> None:
    for variant in (key.lower(), key.upper()):
        root.bind(f"<Control-{variant}>", lambda event: action())


def append_message(text: tk.Text, message: Message, participant_tag: Callable[[str], str]) -> None:
    if message.kind == EVENT:
        append_event(text, message)
        return

    append_chat_header(text, message, participant_tag)
    append_chat_body(text, message)


def append_event(text: tk.Text, message: Message) -> None:
    first, *more = [line.strip() for line in message.body.strip().splitlines() if line.strip()] or [""]

    append_text(text, f"{render.clock(message.created_at)}  •  {first}\n", ("entry", "event"))

    for line in more:
        append_text(text, f"{line}\n", ("event", "event-more"))


def append_chat_header(text: tk.Text, message: Message, participant_tag: Callable[[str], str]) -> None:
    is_question = message.kind == QUESTION
    stamp = f"   #{message.id} · {render.clock(message.created_at)}" if is_question else f"   {render.clock(message.created_at)}"

    append_text(text, "? " if is_question else "", ("entry", "question-mark"))
    append_text(text, message.sender, ("entry", participant_tag(message.sender)))
    append_text(text, " asks " if is_question else " → ", ("muted",))
    append_text(text, participant_label(message.recipient), (participant_tag(message.recipient),))
    append_text(text, stamp + "\n", ("muted",))


def append_chat_body(text: tk.Text, message: Message) -> None:
    tags = ("body", "question") if message.kind == QUESTION else ("body",)

    append_text(text, message.body.strip() + "\n", tags)


def participant_label(name: str) -> str:
    return EVERYONE_LABEL if name == EVERYONE else name


def recipient_name(label: str) -> str:
    return EVERYONE if label == EVERYONE_LABEL else label


def presence_tag(agent: Agent, now: float, starting: bool) -> str:
    if starting:
        return "busy"

    if agent.activity == OFFLINE:
        return "offline"

    if render.is_listening(agent, now):
        return "listening"

    return "busy" if render.is_online(agent, now) else "stale"


def agent_details(agent: Optional[Agent], has_agents: bool, name_tag: str) -> tuple[Segment, ...]:
    if agent is None:
        return ((NO_AGENT_SELECTED_HINT if has_agents else NO_AGENTS_HINT, ("muted",)),)

    facts = f"Provider: {agent.provider or 'not set'}  ·  Role: {agent.role or 'not set'}"
    workdir = f"\nWorking in {agent.workdir}" if agent.workdir else ""

    return (
        (agent.name, ("strong", name_tag)),
        (f"\n{facts}{workdir}", ("muted",)),
        (f"\n{agent.status or 'No status yet.'}", ("paragraph",)),
    )


def question_details(question: Optional[Message], asker_tag: str) -> tuple[Segment, ...]:
    if question is None:
        return ()

    where = f"Goal #{question.goal_id}" if question.goal_id is not None else "General"

    return (
        (f"#{question.id} · ", ("muted",)),
        (question.sender, (asker_tag,)),
        (f" asks · {where} · {render.clock(question.created_at)}", ("muted",)),
        (f"\n{question.body.strip()}", ("paragraph",)),
    )


def new_messages_label(count: int) -> str:
    return f"{count} new message{'s' if count > 1 else ''}  ↓"


def goal_label(goal: Goal) -> str:
    title = f"#{goal.id} {goal.title}"

    return title if goal.status == "active" else f"{status_word(goal.status)} · {title}"


def tasks_tab_label(tasks: list[Task]) -> str:
    if not tasks:
        return "Tasks"

    return f"Tasks {sum(task.status == 'done' for task in tasks)}/{len(tasks)}"


def conversation_title(goal: Optional[Goal]) -> str:
    return "General conversation" if goal is None else f"#{goal.id} {goal.title}"


def conversation_summary(goal: Optional[Goal], tasks: list[Task]) -> str:
    if goal is None:
        return "Messages without a goal"

    return f"{status_word(goal.status)}  ·  {task_progress(tasks)}"


def composer_scope(goal: Optional[Goal]) -> str:
    return "Message in General" if goal is None else f"Message about Goal #{goal.id}"


def goal_details(goal: Optional[Goal]) -> tuple[Segment, ...]:
    if goal is None:
        return ((GENERAL_DETAILS_HINT, ("muted",)),)

    return (
        (f"#{goal.id} {goal.title}", ("strong",)),
        (f"\n{goal.description.strip() or 'No description.'}", ("paragraph",)),
    )


def task_progress(tasks: list[Task]) -> str:
    if not tasks:
        return "No tasks yet"

    return f"{sum(task.status == 'done' for task in tasks)} of {len(tasks)} tasks done"


def task_row(task: Task) -> Row:
    marker, word = TASK_STATES.get(task.status, ("?", task.status))
    tags = ("done",) if task.status == "done" else ()

    return Row(str(task.id), (f"{marker}  #{task.id} {task.title}", word, task.assignee or "unassigned"), tags)


def task_details(task: Optional[Task], has_tasks: bool) -> tuple[Segment, ...]:
    if task is None:
        return ((NO_TASK_SELECTED_HINT if has_tasks else NO_TASKS_HINT, ("muted",)),)

    marker, word = TASK_STATES.get(task.status, ("?", task.status))
    segments = [
        (f"#{task.id} {task.title}", ("strong",)),
        (f"\n{marker} {word}  ·  {task.assignee or 'unassigned'}", ("muted",)),
    ]

    if task.description.strip():
        segments.append((f"\n{task.description.strip()}", ("paragraph",)))

    if task.result.strip():
        segments.append((f"\nResult: {task.result.strip()}", ("paragraph",)))

    return tuple(segments)


def cancel_question(goal: Goal) -> str:
    return f"Cancel goal #{goal.id} “{goal.title}”?\n\nThe agents stop working on it. It stays visible under Show closed."


def status_word(status: str) -> str:
    return status.replace("_", " ").capitalize()


def unseen_badge(unseen: int) -> str:
    return f"● {unseen}" if unseen else ""


def latest_goal_id(store: CoopStore) -> Optional[int]:
    goals = store.list_goals() or store.list_goals(include_closed=True)

    return goals[-1].id if goals else None


def goal_row_id(goal_id: Optional[int]) -> str:
    return GENERAL_ROW if goal_id is None else f"goal-{goal_id}"


def parse_goal_row(row_id: str) -> Optional[int]:
    if row_id == GENERAL_ROW:
        return None

    return int(row_id.removeprefix("goal-"))


def first_line(text: str) -> str:
    line = text.strip().splitlines()[0] if text.strip() else ""

    return line if len(line) <= 100 else line[:97] + "..."


def enable_sharp_text() -> None:
    if sys.platform != "win32":
        return

    import ctypes

    with contextlib.suppress(AttributeError, OSError):
        ctypes.windll.shcore.SetProcessDpiAwareness(1)


def open_window() -> tk.Tk:
    enable_sharp_text()

    try:
        return tk.Tk(className=TITLE)
    except tk.TclError as error:
        raise CoopError(f"Cannot open the dashboard window: {error}.") from error


def run(root: tk.Tk) -> None:
    root.protocol("WM_DELETE_WINDOW", root.quit)
    signal.signal(signal.SIGINT, lambda signum, frame: root.quit())

    root.mainloop()
    root.destroy()


def watch(store: CoopStore, backlog: int) -> None:
    root = open_window()
    CoopDashboard(root, store, backlog)

    run(root)
